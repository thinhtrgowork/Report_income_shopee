import streamlit as st
from datetime import datetime
import pandas as pd
import numpy as np
import plotly.express as px

# Setting API
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import streamlit as st

# Lấy thông tin đăng nhập từ secrets
USERNAME = st.secrets["login"]["username"]
PASSWORD = st.secrets["login"]["password"]

# ===== INIT SESSION =====
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

# ===== ONLY SHOW LOGIN IF NOT LOGGED =====
# ===== ONLY SHOW LOGIN IF NOT LOGGED =====
if not st.session_state.logged_in:

    # ===== CSS UI =====
    st.markdown("""
        <style>
        body {
            background: linear-gradient(135deg, #6366F1, #8B5CF6);
            height: 100vh;
        }
        .login-card {
            background: white;
            padding: 40px 35px;
            border-radius: 20px;
            box-shadow: 0 10px 25px rgba(0,0,0,0.1);
            max-width: 420px;
            margin: 80px auto;
            animation: fadeIn 0.5s ease-in-out;
        }
        @keyframes fadeIn {
            from {opacity:0; transform: translateY(15px);}
            to {opacity:1; transform: translateY(0);}
        }
        .title {
            font-size: 28px;
            font-weight: 700;
            text-align: center;
            margin-bottom: 10px;
            color: #1F2937;
        }
        .subtitle {
            text-align: center;
            font-size: 15px;
            color: #6B7280;
            margin-bottom: 25px;
        }
        </style>
    """, unsafe_allow_html=True)

    # ===== LOGIN CARD WRAPPER =====
    st.markdown("<div class='title'>‼️Đăng nhập để truy cập App‼️",
                unsafe_allow_html=True)
    st.markdown("<div class='subtitle'>Welcome back! Please enter your details.</div>",
                unsafe_allow_html=True)

    username = st.text_input("Username", placeholder="Enter your username")
    password = st.text_input("Password", type="password",
                             placeholder="Enter your password")

    login_btn = st.button("Login", type="primary")

    st.markdown("</div>", unsafe_allow_html=True)

    # ===== LOGIN LOGIC =====
    if login_btn:
        if username == USERNAME and password == PASSWORD:
            st.session_state.logged_in = True
            st.rerun()
        else:
            st.error("❌ Incorrect username or password")

else:
    # ===== Sidebar Logout =====
    if st.session_state.logged_in:
        if st.sidebar.button("🚪 Logout"):
            st.session_state.logged_in = False
            st.rerun()

    def clean_value(x):
        if pd.isna(x):
            return ""
        elif isinstance(x, (int, float)):
            return x  # giữ nguyên kiểu số
        elif isinstance(x, str):
            return x.replace("'", "''")  # escape dấu nháy đơn nếu có
        else:
            return str(x)

    def read_incomedata(df_income, df_all):
        # --- Clean columns ---
        df_income.columns = df_income.columns.str.strip()
        df_all.columns = df_all.columns.str.strip()
        df_all["Actually type"] = df_all["Trạng Thái Đơn Hàng"]
        df_all["Actually type"] = df_all["Actually type"].apply(
            lambda x: (
                "Đơn hàng đã đến User"
                if isinstance(x, str) and "Người mua xác nhận đã nhận được hàng" in x
                else x
            )
        )
        # --- Chỉ lấy dòng cấp Order ---
        df_income = df_income[df_income["Đơn hàng / Sản phẩm"]
                              == "Order"].copy()
        df_income = df_income.drop(columns=["Tên sản phẩm", "Người Mua"])

        # --- Tổng quan ---
        total_revenue = df_income["Giá sản phẩm"].sum()
        total_settlement = df_income["Tổng tiền đã thanh toán"].sum()
        total_fees = total_revenue - total_settlement

        # --- Chuẩn hoá SKU ---
        df_all["SKU Category"] = df_all["SKU phân loại hàng"]

        # --- Merge order + income ---
        df_merged = pd.merge(
            df_income,
            df_all,
            how="left",
            right_on="Mã đơn hàng",
            left_on="Mã đơn hàng",
        )

        # --- Quantity theo SKU ---
        sku_quantity = df_merged.groupby(
            ["SKU Category", "Tên sản phẩm"],
            dropna=False
        ).agg(
            Total_Quantity=("Số lượng", "sum"),
            Total_Orders=("Mã đơn hàng", "nunique")
        ).reset_index()

        # --- Revenue theo SKU ---
        sku_revenue = df_merged.groupby(
            ["SKU Category", "Tên sản phẩm"],
            dropna=False
        ).agg(
            Total_Revenue=("Giá sản phẩm", "sum"),
            Total_Settlement=("Tổng tiền đã thanh toán", "sum")
        ).reset_index()

        # --- Final Report ---
        sku_report = pd.merge(
            sku_quantity,
            sku_revenue,
            on=["SKU Category", "Tên sản phẩm"],
            how="left"
        )

        # --- Summary ---
        summary = {
            "Total_Revenue": total_revenue,
            "Total_Fees": total_fees,
            "Total_Settlement": total_settlement
        }

        return df_income, sku_report, summary, total_revenue, total_fees, total_settlement, df_merged

    def SumQuantityForSKU(df, sku_category):
        # ---- Hoàn thành ----
        df_hoan_thanh = df[
            (df["SKU Category"] == sku_category)
            & (df["Tổng tiền đã thanh toán"] > 0)

        ]

        # ---- Hoàn trả ----
        df_hoan_tra = df[
            (df["SKU Category"] == sku_category)
            & (df["Trạng thái Trả hàng/Hoàn tiền"] == "Đã Chấp Thuận Yêu Cầu")
            & (df_merged["Số lượng sản phẩm được hoàn trả"] != 0)
        ]
        df_all = df[
            (df["SKU Category"] == sku_category)
        ]

        # ---- Kết quả ----
        return {
            "sku": sku_category,
            "hoan_thanh": df_hoan_thanh["Số lượng"].sum(),
            "hoan_tra": df_hoan_tra["Số lượng sản phẩm được hoàn trả"].sum(),
            "tien_quyet_toan": df_all["Tổng tiền đã thanh toán"].sum(),
        }

    try:
        creds_info = st.secrets["google"]

        scope = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]

        credentials = ServiceAccountCredentials.from_json_keyfile_dict(
            creds_info, scope
        )

        client = gspread.authorize(credentials)

        st.success("🔐 Đã đăng nhập và kết nối Google Sheets API thành công!")

    except Exception as e:

        st.error(f"❌ Lỗi khi kết nối Google Sheets API: {e}")

    st.session_state.setdefault("processing", False)
    st.session_state.setdefault("show_warning", True)
    st.session_state.setdefault("income", None)
    st.session_state.setdefault("show_config_ui", True)

    # ===== SETUP GIAO DIỆN =====
    st.set_page_config(page_title="Tool Report Income",
                       layout="centered", page_icon="📊")
    # ===== CSS tuỳ chỉnh =====
    st.markdown(
        """
        <style>
            /* Tổng thể */
            html, body, [class*="css"] {
                font-family: 'Segoe UI', sans-serif;
            }
            h1, h3, h4 {
                color: #333333;
            }
            .centered {
                text-align: center;
            }
            .upload-box {
                border: 2px dashed #cccccc;
                padding: 20px;
                border-radius: 10px;
                background-color: #f9f9f9;
            }
        </style>
    """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
    <div style="text-align: center; margin-top: 10px;">
        <h1 style="
            font-size: 40   px;
            font-weight: 800;
            margin-bottom: 10px;
            background: linear-gradient(90deg, #EE4D2D 0%, #F7B500 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            font-family: 'Segoe UI', sans-serif;
        ">
            Báo cáo doanh thu Shopee
        </h1>
        <p style="
            font-size: 15.5px;
            color: #9ca3af;
            margin-top: -8px;
        ">
            Phân tích doanh thu • Đơn hàng • Khách hàng • SKU
        </p>


    </div>
    """,
        unsafe_allow_html=True
    )

    st.markdown(
        "<hr style='margin-top: 10px; margin-bottom: 30px;'>", unsafe_allow_html=True
    )
    st.sidebar.markdown("### 📤 Tải lên dữ liệu doanh thu bán hàng theo ngày")
    df_income_file = st.sidebar.file_uploader(
        "Upload file Income",
        type=["xlsx", "xls"],
        key="income_file"
    )

    # ===== CẢNH BÁO NẾU CHƯA UPLOAD FILE =====
    if st.session_state.show_warning and df_income_file is None:
        st.markdown("""
            <div style="
                padding: 12px;
                border-radius: 10px;
                background: #FFF4E5;
                border-left: 5px solid #FFA726;
                color: #5A3800;
                font-size: 15px;
                margin: 10px 0;
            ">
                ⚠️ <b>Vui lòng input file trước khi xử lý.</b>
            </div>
        """, unsafe_allow_html=True)

    @st.cache_data(show_spinner="📂 Đang đọc file Income...")
    def load_income(file):
        df = pd.read_excel(
            file,
            sheet_name="Doanh thu",
            dtype={
                "Mã đơn hàng": str,
                "Mã Số Thuế": str,
                "Mã yêu cầu hoàn tiền": str
            }
        )
        df.columns = df.columns.str.strip()
        df["Ngày đặt hàng"] = pd.to_datetime(df["Ngày đặt hàng"])
        return df

    @st.cache_data(show_spinner="📂 Đang đọc file All Orders...")
    def load_all_orders(file):
        df = pd.read_excel(file)
        df.columns = df.columns.str.strip()
        df["SKU Category"] = df["SKU phân loại hàng"]
        return df

    # ===== BUTTON =====
    # ===== BUTTON =====
    if df_income_file is not None:
        df_income = load_income(df_income_file)

        date_min = df_income["Ngày đặt hàng"].min()
        date_max = df_income["Ngày đặt hàng"].max()

        st.write("📅 All Orders từ ngày:", date_min.date())
        st.write("📅 All Orders đến ngày:", date_max.date())

        df_all_file = st.sidebar.file_uploader(
            "Upload file All Order",
            type=["xlsx"],
            key="all_file"
        )

        if df_all_file is not None:
            df_all = load_all_orders(df_all_file)
            list_sku = sorted(df_all["SKU Category"].dropna().unique())

            # ===== FORM CẤU HÌNH – KHÔNG GIẬT =====
            if st.session_state.show_config_ui:
                st.sidebar.markdown("### ⚙️ Cấu hình xử lý")

                sku_info = {}
                for sku in list_sku:
                    sku_info[sku] = st.sidebar.number_input(
                        f"Giá vốn SKU {sku}",
                        min_value=0,
                        step=1000,
                        key=f"cost_{sku}"
                    )
                commission_rate = st.sidebar.number_input(
                    "📊 Tỷ lệ hoa hồng (%)",
                    min_value=0.0,
                    max_value=100.0,
                    value=7.0,
                    step=0.5,
                    format="%.2f"
                )
            process_btn = st.sidebar.button(
                "🚀 Xử lý dữ liệu",
                disabled=st.session_state.processing
            )

            # ===== CHỈ XỬ LÝ KHI SUBMIT FORM =====
            if process_btn:
                st.session_state.processing = True
                st.session_state.show_config_ui = False
                st.session_state.sku_info = sku_info
                st.session_state.commission_rate = commission_rate

                with st.spinner("⏳ Đang xử lý dữ liệu..."):
                    df_income, sku_report, summary, total_revenue, total_fees, total_settlement, df_merged = read_incomedata(
                        df_income, df_all)

                    ket_qua = []
                    for sku in df_merged["SKU Category"].dropna().unique():
                        ket_qua.append(SumQuantityForSKU(df_merged, sku))

                    df_ket_qua = pd.DataFrame(ket_qua)
                    df_ket_qua["Gia_von"] = df_ket_qua["sku"].map(sku_info)
                    df_ket_qua["Total_Cost"] = (
                        df_ket_qua["Gia_von"] * df_ket_qua["hoan_thanh"]
                    )

                st.session_state.income = df_income
                st.session_state.df_merged = df_merged
                st.session_state.df_ket_qua = df_ket_qua

                st.success("✔️ Xử lý dữ liệu thành công!")

            # ===== RESET =====
            reset_btn = st.sidebar.button("🔁 Reset")
            if reset_btn:
                st.session_state.income = None
                st.session_state.processing = False
                st.session_state.show_warning = True
                st.session_state.show_config_ui = True
                st.success(
                    "♻️ Dữ liệu đã được xóa. Bạn có thể upload file khác.")

    if st.session_state.processing:
        report_container = st.container()
        result_box = st.empty()

        with report_container:
            df_income = st.session_state.income
            df_merged = st.session_state.df_merged
            df_ket_qua = st.session_state.df_ket_qua
            commission_rate = st.session_state.commission_rate

            total_revenue = df_income["Giá sản phẩm"].sum()
            total_settlement = df_income["Tổng tiền đã thanh toán"].sum()
            total_fees = total_revenue - total_settlement
            total_VAT = df_income['Thuế GTGT'].sum()
            total_GTGT = df_income['Thuế TNCN'].sum()

            extra_cost = st.session_state.df_ket_qua["Total_Cost"].sum()
            profit = total_settlement - extra_cost

            df = st.session_state.df_ket_qua

            total_tien = df["tien_quyet_toan"].sum()

            df["ty_le"] = 0.0
            if total_tien > 0:
                df["ty_le"] = df["tien_quyet_toan"] / total_tien

            # 3️⃣ Chỉ SKU có giá vốn mới được tính hoa hồng
            mask = df["Gia_von"].notna() & (df["Gia_von"] > 0)

            df["hoa_hong"] = 0.0
            df.loc[mask, "hoa_hong"] = (
                profit * df.loc[mask, "ty_le"] * (commission_rate / 100)
            )

            # 4️⃣ Tổng hoa hồng
            total_commission = df["hoa_hong"].sum()

            day_of_data = df_income["Ngày hoàn thành thanh toán"][0]

            st.info(f"📅 Ngày quyết toán: **{day_of_data}**")
            col1, col2, col3 = st.columns(3)

            with col1:
                st.markdown(
                    f"""
                    <div style="background-color:#e0f7fa; padding:20px; border-radius:10px; text-align:center; box-shadow:2px 2px 10px rgba(0,0,0,0.1);">
                        <div style="font-size:14px; color:#00796b; font-weight:bold;">📝 Tổng doanh thu từ sàn</div>
                        <div style="font-size:26px; font-weight:bold; color:#004d40;">{total_revenue:,.0f} ₫</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            with col2:
                st.markdown(
                    f"""
                    <div style="background-color:#fff3e0; padding:20px; border-radius:10px; text-align:center; box-shadow:2px 2px 10px rgba(0,0,0,0.1);">
                        <div style="font-size:14px; color:#ef6c00; font-weight:bold;">💰 Tổng quyết toán từ sàn</div>
                        <div style="font-size:26px; font-weight:bold; color:#e65100;">{total_settlement:,.0f} ₫</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            with col3:
                st.markdown(
                    f"""
                    <div style="background-color:#ffebee; padding:20px; border-radius:10px; text-align:center; box-shadow:2px 2px 10px rgba(0,0,0,0.1);">
                        <div style="font-size:14px; color:#c62828; font-weight:bold;">📌 Tổng chi phí từ sàn</div>
                        <div style="font-size:26px; font-weight:bold; color:#b71c1c;">{total_fees:,.0f} ₫</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            colfk1, col6, col7, colfk2 = st.columns([0.3, 1, 1, 0.3])

            with col6:
                st.markdown(
                    f"""
                    <div style="background-color:#e0f2f1; padding:20px; border-radius:10px; text-align:center; box-shadow:2px 2px 10px rgba(0,0,0,0.1); margin-top:20px;">
                        <div style="font-size:14px; color:#00695c; font-weight:bold;">‼️ Thuế VAT đã đóng cho sàn </div>
                        <div style="font-size:26px; font-weight:bold; color:#004d40;">{total_VAT:,.0f} ₫</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            with col7:
                st.markdown(
                    f"""
                    <div style="background-color:#fce4ec; padding:20px; border-radius:10px; text-align:center; box-shadow:2px 2px 10px rgba(0,0,0,0.1); margin-top:20px;">
                        <div style="font-size:14px; color:#d81b60; font-weight:bold;">↗️ Thuế GTGT đã đóng cho sàn </div>
                        <div style="font-size:26px; font-weight:bold; color:#c2185b;">{total_GTGT:,.0f} ₫</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            col45, col4, col5 = st.columns(3)

            with col45:
                st.markdown(
                    f"""
                    <div style="background-color: #990033 ; padding:20px; border-radius:10px; text-align:center; box-shadow:2px 2px 10px rgba(0,0,0,0.1); margin-top:40px;">
                        <div style="font-size:18px; color:white; font-weight:bold;">♾️ Chi phí sản xuất</div>
                        <div style="font-size:26px; font-weight:bold; color:white;">{extra_cost:,.0f} ₫</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            with col4:
                st.markdown(
                    f"""
                    <div style="background-color: #339933 ; padding:20px; border-radius:10px; text-align:center; box-shadow:2px 2px 10px rgba(0,0,0,0.1); margin-top:40px;">
                        <div style="font-size:18px; color:white; font-weight:bold;">💵 Lợi nhuận ròng</div>
                        <div style="font-size:26px; font-weight:bold; color:white;">{profit:,.0f} ₫</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            with col5:
                st.markdown(
                    f"""
                    <div style="background-color:#003399; padding:20px; border-radius:10px; text-align:center; box-shadow:2px 2px 10px rgba(0,0,0,0.1); margin-top:40px;">
                        <div style="font-size:18px; color:white; font-weight:bold;">🌹Chi phí hoa hồng</div>
                        <div style="font-size:26px; font-weight:bold; color:white;">{total_commission:,.0f} ₫</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            st.markdown("<br><br>", unsafe_allow_html=True)
            order_col = "Mã đơn hàng"
            chart_df = (
                df_merged.groupby("Actually type")[order_col]
                .nunique()
                .reset_index()
                .rename(columns={order_col: "Đơn hàng (không trùng)"})
            )

            # Tính tổng đơn ban đầu
            total_orders = chart_df["Đơn hàng (không trùng)"].sum()
            chart_df["Phần trăm"] = round(
                chart_df["Đơn hàng (không trùng)"] / total_orders * 100, 1)
            fig = px.pie(
                chart_df,
                names="Actually type",
                values="Đơn hàng (không trùng)",
                color="Actually type",
                color_discrete_map={
                    "Hoàn thành": "#009933",
                    "Đơn hàng đã đến User": "#E9E500",
                    "Đã hủy": "#FF3333",
                },
                hole=0.35
            )
            fig.update_traces(
                text=[f"{p:.0f}%" for p in chart_df["Phần trăm"]],
                textinfo="label+text",
                textfont_size=14,
                pull=[0.02 if s ==
                      "Returned" else 0 for s in chart_df["Actually type"]],
                hovertemplate="%{label}: %{value} đơn<br>Phần trăm: %{text}<extra></extra>"
            )
            fig.update_layout(
                title_text=" ",
                title_font_size=16,
                legend_title_text="Actually type",
                legend_font_size=14,
                margin=dict(t=120, b=40, l=40, r=40),
                width=300,
                height=450
            )

            df_chart = st.session_state.df_ket_qua.copy()
            fig_completed = px.bar(
                df_chart,
                x="sku",
                y="hoan_thanh",
                title="Số lượng hoàn thành theo từng SKU",
                color="sku",
                labels={"sku": "SKU", "hoan_thanh": "Số lượng"},
                text_auto=True
            )
            fig_completed.update_layout(
                xaxis_tickangle=-45,
                height=500,
                margin=dict(t=50, b=50)
            )

            df_percent = df_chart.copy()

            total_qty = df_percent["hoan_thanh"].sum()
            df_percent["ty_le"] = df_percent["hoan_thanh"] / total_qty * 100
            fig_percent_pie = px.pie(
                df_percent,
                names="sku",
                values="hoan_thanh",
                title="Tỷ lệ (%) bán ra theo SKU"
            )

            fig_percent_pie.update_traces(
                textinfo="percent+label"
            )

            # ---- Biểu đồ theo khu vực ----
            region_df = (
                df_merged.groupby("Tỉnh/Thành phố")["Mã đơn hàng"]
                .nunique()
                .reset_index()
                .rename(columns={"Mã đơn hàng": "Đơn hàng"})
            )
            fig_pie = px.pie(
                region_df,
                names="Tỉnh/Thành phố",
                values="Đơn hàng",
                title="Tỷ lệ đơn hàng theo tỉnh",
                hole=0.35,
            )
            fig_pie.update_traces(
                textinfo="percent+label",
                pull=[0.03]*len(region_df),
            )
            fig_pie.update_layout(
                height=480,
                margin=dict(t=120, b=80),
            )

            buyer_df = (
                df_merged.groupby("Người Mua")["Mã đơn hàng"]
                .nunique()
                .reset_index()
                .rename(columns={"Mã đơn hàng": "Đơn hàng"})
            )
            buyer_top10 = buyer_df.nlargest(10, "Đơn hàng")
            fig_buyer_10 = px.bar(
                buyer_top10,
                x="Người Mua",
                y="Đơn hàng",
                title="Số lượng đơn theo từng Buyer",
                color="Người Mua",
                labels={"Người Mua": "Khách mua", "Đơn hàng": "Số đơn"},
                text_auto=True
            )
            fig_buyer_10.update_layout(
                xaxis_tickangle=-45,
                height=500,
                margin=dict(t=50, b=50)
            )

            # ---- Các chi phí trên Sàn TikTok ----
            fee_cols = [
                "Phí vận chuyển Người mua trả",
                "Phí vận chuyển thực tế",
                "Phí vận chuyển được trợ giá từ Shopee",
                "Phí vận chuyển trả hàng (đơn Trả hàng/hoàn tiền)",
                "Phí vận chuyển được hoàn bởi PiShip",
                "Phí vận chuyển trả hàng (đơn giao không thành công)",
                "Sản phẩm được trợ giá từ Shopee",
                "Mã ưu đãi do Người Bán chịu",
                "Mã ưu đãi Đồng Tài Trợ do Người Bán chịu",
                "Mã hoàn xu do Người Bán chịu",
                "Mã hoàn xu Đồng Tài Trợ do Người Bán chịu",
                "Phí cố định",
                "Phí Dịch Vụ",
                "Phí thanh toán",
                "Phí hoa hồng Tiếp thị liên kết",
                "Phí dịch vụ PiShip",
                "Thuế GTGT",
                "Thuế TNCN"
            ]

            fee_sums = df_income[fee_cols].sum().reset_index()
            fee_sums.columns = ["Loại chi phí", "Tổng tiền"]
            fee_sums = fee_sums[fee_sums["Tổng tiền"] != 0]
            fig_fee = px.bar(
                fee_sums,
                x="Tổng tiền",
                y="Loại chi phí",
                orientation="h",
                title="📦 Tổng hợp chi phí theo loại (Các loại chi phí khác 0)",
                labels={
                    "Tổng tiền": "Tổng tiền (₫)", "Loại chi phí": "Danh mục chi phí"},
            )
            fig_fee.update_layout(
                height=900,  # Cho 34 cột nhìn dễ
                xaxis_tickformat=",",
            )
            # ---- Biểu đồ số lượng đơn theo Buyer ----
            st.markdown("### 📊 Phân bố trạng thái đơn hàng")
            st.plotly_chart(fig)

            st.markdown("### 📊 Biểu đồ số lượng sản phẩm hoàn thành")
            st.plotly_chart(fig_completed)
            st.plotly_chart(fig_percent_pie)

            st.markdown("### 🥧 Biểu đồ tỷ lệ đơn hàng theo khu vực")
            st.plotly_chart(fig_pie)

            st.markdown("### 📊 Biểu đồ số lượng đơn của Khách mua")
            st.plotly_chart(fig_buyer_10)

            st.plotly_chart(fig_fee, use_container_width=True)

            # ---- Lấy thông tin ghi vafp GGSHEET ----
            fill_ggsheet = pd.DataFrame([{
                "Ngày thanh toán": day_of_data,
                "Tổng doanh thu": total_revenue,
                "Tổng quyết toán": total_settlement,
                "Tổng chi phí sàn": total_fees,
                "Thuế VAT đã đóng": total_VAT,
                "Thuế GTGT đã đóng": total_GTGT,
                "Chi phí khác": extra_cost,
                "Lợi nhuận ròng": profit,
                "Chi phí hoa hồng": total_commission,
            }])

            st.session_state["fill_ggsheet"] = (fill_ggsheet)

            st.markdown("### 📄 Bảng thống kê SKU")
            st.dataframe(st.session_state.df_ket_qua)

            st.markdown("### 📄 Danh sách đơn hàng")
            st.dataframe(st.session_state.df_merged)

        if st.button("📤 Ghi dữ liệu doanh thu vào Google Sheet"):
            with result_box:
                with st.spinner("⏳ Đang ghi dữ liệu..."):
                    spreadsheet = client.open_by_url(
                        "https://docs.google.com/spreadsheets/d/1ufSZHqoqwTcfvP0RhTq-RK9FatGkmmT2cUdegKi3H1U/edit?usp=sharing"
                    )
                    worksheet = spreadsheet.worksheet("Sheet1")
                    existing_data = worksheet.get_all_values()
                    next_row_index = None
                    for i in range(1, len(existing_data)):
                        if all(cell.strip() == "" for cell in existing_data[i]):
                            next_row_index = i + 1
                            break
                    if next_row_index is None:
                        next_row_index = len(existing_data) + 1

                    from gspread_dataframe import set_with_dataframe
                    df_to_write = pd.DataFrame([{
                        col: clean_value(val)
                        for col, val in zip(
                            st.session_state["fill_ggsheet"].columns,
                            st.session_state["fill_ggsheet"].iloc[0]
                        )
                    }])

                    set_with_dataframe(
                        worksheet, df_to_write,
                        row=next_row_index,
                        include_column_header=False
                    )

            with result_box:
                st.success("✅ Dữ liệu đã được ghi vào Google Sheet!")
