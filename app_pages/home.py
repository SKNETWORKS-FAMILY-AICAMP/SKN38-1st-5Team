import streamlit as st

import home_extras
from db import queries as q
from ui import district_row, load_frame

ranking = load_frame(q.get_district_ranking)
if ranking.empty:
    st.info("동네 판정 자료가 없어요.")
    st.stop()

region_id = int(st.session_state.district_id)
row = district_row(ranking, region_id)
home_extras.render(row, ranking)
