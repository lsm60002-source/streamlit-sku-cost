import streamlit as st
import pandas as pd
from datetime import datetime
import io

# ----------------------------
# Optional dependency check
# ----------------------------
def has_openpyxl() -> bool:
    try:
        import openpyxl  # noqa: F401
        return True
    except Exception:
        return False

OPENPYXL_OK = has_openpyxl()

# ----------------------------
# Page config
# ----------------------------
st.set_page_config(page_title="SKU 원가 매핑 시스템", layout="wide")

# ----------------------------
# Columns / Defaults
# ----------------------------
TEST_STORES_DEFAULT = ["테스트점포1", "테스트점포2", "테스트점포3"]

BASE_COLUMNS = [
    "점포", "SKU코드", "SKU명", "판매가", "레시피코드", "원재료비",
    "인건비(추정)", "총원가", "원가율(%)", "최종수정일"
]

# ----------------------------
# Session state init
# ----------------------------
if "mapping_data" not in st.session_state:
    st.session_state.mapping_data = pd.DataFrame(columns=BASE_COLUMNS)

if "version_history" not in st.session_state:
    st.session_state.version_history = []

if "stores" not in st.session_state:
    st.session_state.stores = TEST_STORES_DEFAULT.copy()

# ----------------------------
# Helpers
# ----------------------------
def ensure_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure required columns exist; keep extra columns if present."""
    for c in BASE_COLUMNS:
        if c not in df.columns:
            df[c] = None
    ordered = [c for c in BASE_COLUMNS if c in df.columns] + [c for c in df.columns if c not in BASE_COLUMNS]
    return df[ordered]

def compute_cost_fields(df: pd.DataFrame) -> pd.DataFrame:
    """Compute 총원가, 원가율(%), 최종수정일."""
    df = df.copy()

    # numeric coerce
    for col in ["판매가", "원재료비", "인건비(추정)"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    df["총원가"] = df["원재료비"] + df["인건비(추정)"]
    df["원가율(%)"] = (df["총원가"] / df["판매가"].replace(0, pd.NA) * 100).round(1)
    df["원가율(%)"] = df["원가율(%)"].fillna(0)
    df["최종수정일"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    return df

def df_to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8-sig")

def df_to_xlsx_bytes(df: pd.DataFrame) -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="데이터")
    return buffer.getvalue()

def read_uploaded_file(uploaded_file) -> pd.DataFrame:
    name = uploaded_file.name.lower()
    if name.endswith(".csv"):
        return pd.read_csv(uploaded_file)
    if name.endswith(".xlsx") or name.endswith(".xls"):
        if not OPENPYXL_OK:
            raise RuntimeError("xlsx 파일을 읽으려면 openpyxl이 필요합니다. CSV로 업로드해주세요.")
        return pd.read_excel(uploaded_file)
    raise RuntimeError("지원하지 않는 파일 형식입니다. CSV(권장) 또는 XLSX를 사용해주세요.")

def normalize_store_list_from_data():
    """데이터에 있는 점포를 stores에 반영(유니크)."""
    if st.session_state.mapping_data.empty:
        return
    df = st.session_state.mapping_data
    if "점포" in df.columns:
        vals = df["점포"].dropna().astype(str).str.strip()
        vals = [v for v in vals.unique().tolist() if v]
        merged = list(dict.fromkeys(st.session_state.stores + vals))
        st.session_state.stores = merged

def filter_by_store(df: pd.DataFrame, store: str) -> pd.DataFrame:
    df = ensure_columns(df)
    if store == "전체":
        return df
    return df[df["점포"].astype(str) == store]

def store_summary(df: pd.DataFrame) -> pd.DataFrame:
    """점포별 KPI 요약."""
    if df.empty:
        return pd.DataFrame(columns=["점포", "SKU수", "평균원가율", "고원가율(>=80%)", "위험(>=100%)"])
    tmp = df.copy()
    tmp["원가율(%)"] = pd.to_numeric(tmp["원가율(%)"], errors="coerce").fillna(0)
    g = tmp.groupby("점포", dropna=False)
    out = pd.DataFrame({
        "SKU수": g.size(),
        "평균원가율": g["원가율(%)"].mean().round(1),
        "고원가율(>=80%)": g.apply(lambda x: (x["원가율(%)"] >= 80).sum()),
        "위험(>=100%)": g.apply(lambda x: (x["원가율(%)"] >= 100).sum()),
    }).reset_index()
    out.rename(columns={"점포": "점포"}, inplace=True)
    out = out.sort_values(["위험(>=100%)", "고원가율(>=80%)", "SKU수"], ascending=False)
    return out

# ----------------------------
# Sidebar: Store selection + Store admin
# ----------------------------
with st.sidebar:
    st.header("점포 선택")

    normalize_store_list_from_data()

    store_options = ["전체"] + st.session_state.stores
    selected_store = st.selectbox("조회/입력 기준 점포", store_options, index=0)

    st.divider()
    st.subheader("테스트 점포 관리")

    with st.expander("점포 추가/수정"):
        new_store = st.text_input("점포명 추가", placeholder="예: 테스트점포4")
        if st.button("점포 추가"):
            ns = (new_store or "").strip()
            if not ns:
                st.warning("점포명을 입력해주세요.")
            else:
                if ns not in st.session_state.stores:
                    st.session_state.stores.append(ns)
                    st.success("점포가 추가되었습니다.")
                    st.rerun()
                else:
                    st.info("이미 존재하는 점포명입니다.")

        st.caption("점포 3개만 쓰려면 기본값(테스트점포1~3)만 두고 추가하지 않으면 됩니다.")

    st.divider()

    if not OPENPYXL_OK:
        st.info("openpyxl이 없어 XLSX 업로드/다운로드는 비활성화됩니다. CSV로 사용하세요.")

# ----------------------------
# Title
# ----------------------------
st.title("스낵픽 SKU-원가 매핑 시스템")
st.markdown("파일럿 전용 | 점포별 수기 매핑 관리 도구")

# ----------------------------
# Tabs
# ----------------------------
tab1, tab2, tab3, tab4 = st.tabs(["매핑 관리", "이상치 분석", "버전 관리", "데이터 업로드"])

# ============================
# TAB 1: 매핑 관리
# ============================
with tab1:
    st.header("SKU-레시피 매핑")

    col1, col2 = st.columns([2, 1])

    with col1:
        st.subheader("신규 매핑 추가")

        # 입력 시 점포는 "전체"면 선택 필요, 아니면 선택된 점포로 고정
        if selected_store == "전체":
            store_for_input = st.selectbox("입력할 점포", st.session_state.stores)
        else:
            store_for_input = selected_store
            st.caption(f"현재 선택 점포({selected_store})로 입력됩니다.")

        with st.form("add_mapping"):
            cols = st.columns(3)
            sku_code = cols[0].text_input("SKU 코드", placeholder="예: SNK001")
            sku_name = cols[1].text_input("SKU 명", placeholder="예: 김치볶음밥")
            selling_price = cols[2].number_input("판매가 (원)", min_value=0, value=5000)

            cols2 = st.columns(3)
            recipe_code = cols2[0].text_input("레시피 코드", placeholder="예: RCP001")
            material_cost = cols2[1].number_input("원재료비 (원)", min_value=0, value=2000)
            labor_cost = cols2[2].number_input("인건비 추정 (원)", min_value=0, value=800)

            submitted = st.form_submit_button("매핑 추가")

            if submitted:
                if store_for_input and sku_code and sku_name and recipe_code:
                    total_cost = material_cost + labor_cost
                    cost_ratio = (total_cost / selling_price * 100) if selling_price > 0 else 0

                    new_row = pd.DataFrame([{
                        "점포": str(store_for_input).strip(),
                        "SKU코드": sku_code,
                        "SKU명": sku_name,
                        "판매가": selling_price,
                        "레시피코드": recipe_code,
                        "원재료비": material_cost,
                        "인건비(추정)": labor_cost,
                        "총원가": total_cost,
                        "원가율(%)": round(cost_ratio, 1),
                        "최종수정일": datetime.now().strftime("%Y-%m-%d %H:%M")
                    }])

                    st.session_state.mapping_data = pd.concat(
                        [st.session_state.mapping_data, new_row],
                        ignore_index=True
                    )
                    normalize_store_list_from_data()
                    st.success(f"[{store_for_input}] {sku_name} 매핑 완료")
                else:
                    st.error("필수 항목(점포, SKU코드, SKU명, 레시피코드)을 입력해주세요.")

    with col2:
        st.subheader("빠른 통계 (선택 점포 기준)")
        df_scope = filter_by_store(st.session_state.mapping_data, selected_store)

        if not df_scope.empty:
            st.metric("매핑 SKU", len(df_scope))
            avg_cost_ratio = pd.to_numeric(df_scope["원가율(%)"], errors="coerce").mean()
            st.metric("평균 원가율", f"{avg_cost_ratio:.1f}%")

            high_cost = (pd.to_numeric(df_scope["원가율(%)"], errors="coerce").fillna(0) >= 80).sum()
            critical = (pd.to_numeric(df_scope["원가율(%)"], errors="coerce").fillna(0) >= 100).sum()

            st.metric("고원가율(>=80%)", int(high_cost))
            st.metric("위험(>=100%)", int(critical))
        else:
            st.info("해당 범위에 데이터가 없습니다.")

    st.divider()
    st.subheader("현재 매핑 현황")

    df_scope = filter_by_store(st.session_state.mapping_data, selected_store)

    if not df_scope.empty:
        edited_df = st.data_editor(
            df_scope,
            hide_index=True,
            use_container_width=True,
            num_rows="dynamic",
            column_config={
                "원가율(%)": st.column_config.ProgressColumn(
                    "원가율(%)",
                    format="%.1f%%",
                    min_value=0,
                    max_value=150,
                ),
                "판매가": st.column_config.NumberColumn("판매가", format="₩%d"),
                "총원가": st.column_config.NumberColumn("총원가", format="₩%d"),
            }
        )

        # 저장 로직: 선택 점포 범위만 덮어쓰기
        if st.button("변경사항 저장"):
            edited_df = ensure_columns(edited_df)

            # 전체 데이터에서 현재 scope 제외 후, edited_df로 대체
            full = ensure_columns(st.session_state.mapping_data)
            if selected_store == "전체":
                st.session_state.mapping_data = edited_df
            else:
                full_other = full[full["점포"].astype(str) != selected_store]
                st.session_state.mapping_data = pd.concat([full_other, edited_df], ignore_index=True)

            st.success("저장 완료")
            st.rerun()

        st.markdown("다운로드 (선택 점포 기준)")
        dl_col1, dl_col2 = st.columns(2)

        with dl_col1:
            st.download_button(
                label="CSV 다운로드",
                data=df_to_csv_bytes(edited_df),
                file_name=f"원가매핑_{selected_store}_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv"
            )

        with dl_col2:
            if OPENPYXL_OK:
                st.download_button(
                    label="XLSX 다운로드",
                    data=df_to_xlsx_bytes(edited_df),
                    file_name=f"원가매핑_{selected_store}_{datetime.now().strftime('%Y%m%d')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            else:
                st.caption("XLSX 다운로드는 openpyxl이 있는 환경에서만 가능합니다.")
    else:
        st.info("표시할 데이터가 없습니다. 점포를 바꾸거나 위에서 추가해주세요.")

# ============================
# TAB 2: 이상치 분석
# ============================
with tab2:
    st.header("이상치 분석")

    df_all = ensure_columns(st.session_state.mapping_data)
    df_scope = filter_by_store(df_all, selected_store)

    if df_all.empty:
        st.info("분석할 데이터가 없습니다.")
    else:
        # 2-1) 점포별 요약은 항상 전체 기준으로 보여주면 편함
        st.subheader("점포별 요약")
        summary = store_summary(df_all)
        st.dataframe(summary, use_container_width=True, hide_index=True)

        st.divider()

        # 2-2) 선택 점포 기준 상세
        st.subheader(f"선택 점포 상세 ({selected_store})")

        if df_scope.empty:
            st.info("해당 범위에 데이터가 없습니다.")
        else:
            df = df_scope.copy()
            df["원가율(%)"] = pd.to_numeric(df["원가율(%)"], errors="coerce").fillna(0)

            st.markdown("즉시 검토 대상")
            critical = df[df["원가율(%)"] >= 100]
            if not critical.empty:
                st.error(f"원가율 100% 이상 SKU: {len(critical)}개")
                st.dataframe(
                    critical[["점포", "SKU명", "판매가", "총원가", "원가율(%)"]],
                    use_container_width=True,
                    hide_index=True
                )
            else:
                st.success("원가율 100% 이상 SKU 없음")

            st.divider()

            c1, c2 = st.columns(2)
            with c1:
                st.markdown("월 마감 시 검토 대상 (80% 이상)")
                high_cost = df[df["원가율(%)"] >= 80].sort_values("원가율(%)", ascending=False)
                if not high_cost.empty:
                    st.warning(f"{len(high_cost)}개 발견")
                    st.dataframe(
                        high_cost[["점포", "SKU명", "원가율(%)"]].head(20),
                        use_container_width=True,
                        hide_index=True
                    )
                else:
                    st.success("없음")

            with c2:
                st.markdown("원가율 분포")
                bins = [0, 60, 80, 100, 150]
                labels = ["양호(<60%)", "주의(60-80%)", "경고(80-100%)", "위험(100%+)"]
                df["구간"] = pd.cut(df["원가율(%)"], bins=bins, labels=labels, include_lowest=True)
                distribution = df["구간"].value_counts().reindex(labels, fill_value=0)
                st.bar_chart(distribution)

            st.divider()
            st.subheader("상세 통계")
            cols = st.columns(4)
            cols[0].metric("평균 원가율", f"{df['원가율(%)'].mean():.1f}%")
            cols[1].metric("중위값", f"{df['원가율(%)'].median():.1f}%")
            cols[2].metric("최고", f"{df['원가율(%)'].max():.1f}%")
            cols[3].metric("최저", f"{df['원가율(%)'].min():.1f}%")

# ============================
# TAB 3: 버전 관리
# ============================
with tab3:
    st.header("버전 관리")

    df_all = ensure_columns(st.session_state.mapping_data)
    df_scope = filter_by_store(df_all, selected_store)

    c1, c2 = st.columns([3, 1])

    with c1:
        st.subheader("현재 상태 스냅샷 저장 (선택 점포 기준)")

        with st.form("save_version"):
            version_name = st.text_input(
                "버전명",
                value=f"{selected_store}_원가기준표_{datetime.now().strftime('%Y-%m')}"
            )
            version_note = st.text_area("변경 사항 메모", placeholder="예: 12월 레시피 변경 반영")
            save_version = st.form_submit_button("버전 저장")

            if save_version:
                if df_scope.empty:
                    st.error("저장할 데이터가 없습니다.")
                else:
                    version_data = {
                        "scope_store": selected_store,
                        "version_name": version_name,
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "note": version_note,
                        "data": df_scope.copy(),
                        "sku_count": len(df_scope)
                    }
                    st.session_state.version_history.append(version_data)
                    st.success(f"'{version_name}' 버전 저장 완료")

    with c2:
        st.metric("저장된 버전", len(st.session_state.version_history))

    st.divider()
    st.subheader("버전 히스토리 (선택 점포 기준으로 필터)")

    # 선택 점포가 전체면 전부 보여주고, 아니면 해당 점포/해당 범위 버전만 보여줌
    versions = st.session_state.version_history
    if selected_store != "전체":
        versions = [v for v in versions if v.get("scope_store") == selected_store]

    if versions:
        for idx, version in enumerate(reversed(versions)):
            exp_title = f"{version['version_name']} ({version['timestamp']})"
            with st.expander(exp_title):
                st.markdown(f"범위: {version.get('scope_store', '-')}")
                st.markdown(f"메모: {version.get('note') or '-'}")
                st.markdown(f"SKU 개수: {version.get('sku_count', 0)}")

                b1, b2 = st.columns(2)

                with b1:
                    if st.button("이 버전으로 복원", key=f"restore_{idx}"):
                        snap = ensure_columns(version["data"])

                        full = ensure_columns(st.session_state.mapping_data)
                        scope = version.get("scope_store", "전체")

                        if scope == "전체":
                            st.session_state.mapping_data = snap
                        else:
                            full_other = full[full["점포"].astype(str) != scope]
                            st.session_state.mapping_data = pd.concat([full_other, snap], ignore_index=True)

                        st.success("복원 완료")
                        st.rerun()

                with b2:
                    st.download_button(
                        label="CSV 다운로드",
                        data=df_to_csv_bytes(version["data"]),
                        file_name=f"{version['version_name']}.csv",
                        mime="text/csv",
                        key=f"download_csv_{idx}"
                    )
                    if OPENPYXL_OK:
                        st.download_button(
                            label="XLSX 다운로드",
                            data=df_to_xlsx_bytes(version["data"]),
                            file_name=f"{version['version_name']}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            key=f"download_xlsx_{idx}"
                        )
    else:
        st.info("저장된 버전이 없습니다.")

# ============================
# TAB 4: 데이터 업로드
# ============================
with tab4:
    st.header("데이터 일괄 업로드")

    st.markdown(
        "업로드 파일에는 다음 컬럼이 포함되어야 합니다:\n"
        "- 점포, SKU코드, SKU명, 판매가, 레시피코드, 원재료비, 인건비(추정)\n\n"
        "CSV 업로드를 권장합니다."
    )

    # Sample template (점포 포함)
    sample_data = pd.DataFrame({
        "점포": ["테스트점포1", "테스트점포1", "테스트점포2"],
        "SKU코드": ["SNK001", "SNK002", "SNK003"],
        "SKU명": ["김치볶음밥", "제육볶음", "샐러드"],
        "판매가": [5000, 6000, 4500],
        "레시피코드": ["RCP001", "RCP002", "RCP003"],
        "원재료비": [2000, 2500, 1800],
        "인건비(추정)": [800, 1000, 600],
    })

    st.markdown("샘플 양식 다운로드")
    s1, s2 = st.columns(2)

    with s1:
        st.download_button(
            label="샘플 CSV 다운로드",
            data=df_to_csv_bytes(sample_data),
            file_name="매핑_업로드_양식.csv",
            mime="text/csv"
        )

    with s2:
        if OPENPYXL_OK:
            st.download_button(
                label="샘플 XLSX 다운로드",
                data=df_to_xlsx_bytes(sample_data),
                file_name="매핑_업로드_양식.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.caption("샘플 XLSX는 openpyxl이 있는 환경에서만 제공됩니다.")

    st.divider()

    allow_types = ["csv"]
    if OPENPYXL_OK:
        allow_types += ["xlsx", "xls"]

    uploaded_file = st.file_uploader("파일 업로드", type=allow_types)

    if uploaded_file:
        try:
            df_upload = read_uploaded_file(uploaded_file)
            df_upload = ensure_columns(df_upload)

            st.subheader("미리보기")
            st.dataframe(df_upload.head(), use_container_width=True)

            replace = st.radio("기존 데이터 처리", ["교체", "추가"], horizontal=True)

            if st.button("데이터 불러오기"):
                # 필수: 점포 존재
                if df_upload["점포"].isna().all():
                    st.error("업로드 데이터에 '점포' 컬럼 값이 없습니다.")
                else:
                    df_upload["점포"] = df_upload["점포"].astype(str).str.strip()
                    df_upload = compute_cost_fields(df_upload)
                    df_upload = ensure_columns(df_upload)

                    if replace == "교체":
                        st.session_state.mapping_data = df_upload
                    else:
                        st.session_state.mapping_data = pd.concat(
                            [ensure_columns(st.session_state.mapping_data), df_upload],
                            ignore_index=True
                        )
                        st.session_state.mapping_data = ensure_columns(st.session_state.mapping_data)

                    normalize_store_list_from_data()
                    st.success(f"{len(df_upload)}개 SKU 매핑 반영 완료")
                    st.rerun()

        except Exception as e:
            st.error(f"업로드 처리 오류: {e}")

# ----------------------------
# Sidebar: Reset
# ----------------------------
with st.sidebar:
    st.divider()
    if st.button("전체 데이터 초기화", type="secondary"):
        confirm = st.checkbox("정말 초기화하시겠습니까?")
        if confirm:
            st.session_state.mapping_data = pd.DataFrame(columns=BASE_COLUMNS)
            st.session_state.version_history = []
            st.session_state.stores = TEST_STORES_DEFAULT.copy()
            st.success("초기화 완료")
            st.rerun()
