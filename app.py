"""Service point map. Run locally with: streamlit run app.py"""

from html import escape
from pathlib import Path

import pandas as pd
import streamlit as st
import folium
from branca.element import MacroElement, Template
from folium.plugins import Fullscreen, MarkerCluster
from streamlit_folium import st_folium

from data_loader import load_data

st.set_page_config(page_title="Service Point Map", layout="wide")
st.html("<style>" + Path(__file__).with_name("styles.css").read_text(encoding="utf-8-sig") + "</style>")
st.sidebar.markdown(
    '<div class="brand"><div class="brand-mark">sp</div><div>'
    '<div class="brand-title">Service points</div>'
    '<div class="brand-subtitle">NETWORK EXPLORER</div></div></div>',
    unsafe_allow_html=True,
)
summary = st.sidebar.empty()
df = load_data()


def options_for(column: str, filtered_df: pd.DataFrame) -> list:
    return sorted(filtered_df[column].dropna().unique().tolist())


def coordinate_filter(axis, label, limit):
    values = df.loc[df[axis].between(-limit, limit), axis].dropna()
    bounds = (float(values.min()), float(values.max())) if not values.empty else (-limit, limit)
    low, high = st.session_state.get(f"{axis}_range", bounds)
    low, high = (max(bounds[0], min(value, bounds[1])) for value in (low, high))
    st.session_state[f"{axis}_range"] = (low, high)
    if bounds[0] < bounds[1]:
        st.slider(
            f"{label} range", bounds[0], bounds[1],
            key=f"{axis}_range", step=0.000001, format="%.6f",
        )
    return st.session_state[f"{axis}_range"]


with st.sidebar.expander("Search by coordinates", expanded=True):
    left, right = st.columns(2)
    search_latitude = left.number_input(
        "Latitude", min_value=-90.0, max_value=90.0, value=None,
        step=0.000001, format="%.6f", key="search_latitude",
    )
    search_longitude = right.number_input(
        "Longitude", min_value=-180.0, max_value=180.0, value=None,
        step=0.000001, format="%.6f", key="search_longitude",
    )
    lat_range = coordinate_filter("latitude", "Latitude", 90.0)
    lon_range = coordinate_filter("longitude", "Longitude", 180.0)
filtered = df.copy()
with st.sidebar.expander("Location filters", expanded=True):
    selected_division = st.multiselect("Division", options_for("division", df))
    if selected_division:
        filtered = filtered[filtered["division"].isin(selected_division)]
    selected_district = st.multiselect("District", options_for("district", filtered))
    if selected_district:
        filtered = filtered[filtered["district"].isin(selected_district)]
    selected_upazila = st.multiselect("Upazila / Thana", options_for("upazila_thana", filtered))
    if selected_upazila:
        filtered = filtered[filtered["upazila_thana"].isin(selected_upazila)]
    selected_union = st.multiselect("Union / Ward", options_for("union_ward", filtered))
    if selected_union:
        filtered = filtered[filtered["union_ward"].isin(selected_union)]

with st.sidebar.expander("Service filters"):
    selected_type = st.multiselect("Service Point Type", options_for("service_point_type", df))
    if selected_type:
        filtered = filtered[filtered["service_point_type"].isin(selected_type)]
    selected_project = st.multiselect("Project", options_for("project", df))
    if selected_project:
        filtered = filtered[filtered["project"].isin(selected_project)]

filtered = filtered[
    filtered["latitude"].between(*lat_range) & filtered["longitude"].between(*lon_range)
]
summary.markdown(
    f'<div class="network-summary"><div class="summary-label">SERVICE POINTS IN VIEW</div>'
    f'<div class="summary-value">{len(filtered):,} <span>/ {len(df):,}</span></div>'
    f'<div class="summary-foot"><i></i>{filtered["district"].nunique()} districts · Current filters</div></div>',
    unsafe_allow_html=True,
)
st.html(
    f'<div class="explorer-bar"><div><h1>Service point explorer</h1>'
    f'<p>Find a location. Connect to services.</p></div>'
    f'<div class="view-badge"><i></i>{len(filtered):,}<span class="badge-label"> locations in view</span></div></div>'
)

mappable = filtered[
    filtered["latitude"].between(-90, 90) & filtered["longitude"].between(-180, 180)
]
if mappable.empty:
    st.sidebar.warning("No service points match the current filters.")
    center = [23.685, 90.3563]
else:
    center = [mappable["latitude"].mean(), mappable["longitude"].mean()]

search_location = (
    [search_latitude, search_longitude]
    if search_latitude is not None and search_longitude is not None else None
)

# Match the six-decimal precision shown by the inputs, including rounded sheet values.
matched_position = None
if search_location:
    coordinate_matches = (
        (mappable["latitude"] - search_latitude).abs().le(0.0000005001)
        & (mappable["longitude"] - search_longitude).abs().le(0.0000005001)
    )
    matched_position = next((i for i, matches in enumerate(coordinate_matches) if matches), None)
    if matched_position is not None:
        matched_row = mappable.iloc[matched_position]
        search_location = [float(matched_row["latitude"]), float(matched_row["longitude"])]

m = folium.Map(
    location=search_location or center, zoom_start=15 if search_location else 8, tiles="OpenStreetMap",
    zoom_control=True, scroll_wheel_zoom=True,
    inertia=True, world_copy_jump=True, zoom_snap=0.5,
    zoom_delta=0.5, wheel_debounce_time=80, wheel_px_per_zoom_level=120,
)
Fullscreen(position="topright").add_to(m)
if search_location and matched_position is None:
    folium.CircleMarker(
        search_location, radius=7, color="#dc2626", fill=True, fill_opacity=0.8,
        tooltip=f"{search_latitude:.6f}, {search_longitude:.6f}",
    ).add_to(m)
cluster = MarkerCluster(show_coverage_on_hover=False, chunked_loading=True).add_to(m)


def val(row, col):
    value = row.get(col, "")
    return "" if pd.isna(value) else escape(str(value))


selected_marker = None
for position, (_, row) in enumerate(mappable.iterrows()):
    is_match = position == matched_position
    details = "".join(
        f'<div class="detail-row"><dt>{label}</dt><dd>{val(row, field)}</dd></div>'
        for label, field in [
            ("Project", "project"), ("Division", "division"), ("District", "district"),
            ("Upazila / Thana", "upazila_thana"), ("Union / Ward", "union_ward"),
            ("Address", "address_details"), ("Contact", "contact"), ("Email", "email"),
        ] if val(row, field)
    )
    popup_html = f"""
        <article class="location-card">
            <div class="card-eyebrow">{val(row, 'service_point_type')} · {val(row, 'code')}</div>
            <h2>{val(row, 'service_point_name') or 'Service point'}</h2>
            <div class="status-badge">{val(row, 'service_status') or 'Status unavailable'}</div>
            <dl>{details}</dl>
            <div class="card-coordinates">{row['latitude']:.6f}, {row['longitude']:.6f}</div>
        </article>
    """
    pin_color = "#be3666" if is_match else "#0f766e"
    marker = folium.Marker(
        location=[row["latitude"], row["longitude"]],
        tooltip=folium.Tooltip(val(row, "service_point_name") or "Service point", sticky=False),
        popup=folium.Popup(popup_html, max_width=310, min_width=230, max_height=370,
                           auto_pan_padding=[24, 24]),
        icon=folium.DivIcon(
            html=f'<svg width="30" height="36" viewBox="0 0 30 36" aria-hidden="true">'
                 f'<path d="M15 1C7.3 1 1 7.3 1 15c0 9 14 20 14 20s14-11 14-20C29 7.3 22.7 1 15 1Z" '
                 f'fill="{pin_color}" stroke="white" stroke-width="2"/>'
                 '<path d="M15 9v12M9 15h12" stroke="white" stroke-width="2.5" stroke-linecap="round"/></svg>',
            class_name="service-point-marker selected-marker" if is_match else "service-point-marker",
            icon_size=(30, 36), icon_anchor=(15, 35), popup_anchor=(0, -31),
        ),
    ).add_to(cluster)
    if is_match:
        selected_marker = marker

# Leaflet must update its pixel geometry after sidebar/fullscreen/viewport resizing.
# Resize only the container, never the translated map panes used during dragging.
responsive = MacroElement()
responsive.selected_marker = selected_marker
responsive.cluster = cluster
responsive._template = Template("""
{% macro header(this, kwargs) %}
<style>
    .leaflet-container { font-family: "Segoe UI", Arial, sans-serif; background: #e8eeef; }
    .service-point-marker { filter: drop-shadow(0 2px 3px rgba(17,43,60,.22)); }
    .marker-cluster-small, .marker-cluster-medium, .marker-cluster-large { background: rgba(15,118,110,.17); }
    .marker-cluster-small div, .marker-cluster-medium div, .marker-cluster-large div {
        background: #fff; color: #0c655d; border: 1px solid #b3d6ce;
        font-family: "Segoe UI", Arial, sans-serif; font-size: 12px; font-weight: 700;
        box-shadow: 0 2px 5px #15364d16;
    }
    .leaflet-bar { border: 1px solid #dce4e9 !important; border-radius: 10px !important;
        overflow: hidden; box-shadow: 0 3px 12px #17304714 !important; }
    .leaflet-bar a { width: 36px !important; height: 36px !important; line-height: 36px !important;
        color: #274c60 !important; background-color: white !important; border-color: #e5eaef !important; }
    .leaflet-top .leaflet-control { margin-top: 18px; }
    .leaflet-left .leaflet-control { margin-left: 18px; }
    .leaflet-right .leaflet-control { margin-right: 18px; }
    .leaflet-popup-content-wrapper { border-radius: 13px; padding: 0;
        box-shadow: 0 8px 32px #142e4830, 0 0 0 1px #dce5eb; }
    .leaflet-popup-content { margin: 0; max-width: calc(100vw - 76px); }
    .leaflet-popup-scrolled { border: 0; }
    .leaflet-container a.leaflet-popup-close-button { right: 8px; top: 8px; color: #748495;
        width: 24px; height: 24px; border-radius: 50%; font-size: 20px; z-index: 1; }
    .leaflet-container a.leaflet-popup-close-button:hover { background: #eaf0f4; color: #172b42; }
    .location-card { padding: 22px; color: #253c50; min-width: 218px; box-sizing: border-box; }
    .card-eyebrow { color: #758498; font-size: 9px; font-weight: 650; letter-spacing: 1px;
        text-transform: uppercase; padding-right: 12px; }
    .location-card h2 { font-size: 17px; line-height: 1.35; color: #172b42;
        font-weight: 700; margin: 7px 0 10px; letter-spacing: -.3px; }
    .status-badge { display: inline-block; background: #edf4f7; color: #3e6073;
        padding: 4px 9px; font-size: 10px; border-radius: 5px; }
    .location-card dl { margin: 16px 0 12px; border-top: 1px solid #e9eef2; padding-top: 12px; }
    .detail-row { display: grid; grid-template-columns: 82px minmax(0,1fr); gap: 10px;
        font-size: 11px; line-height: 1.5; margin-bottom: 8px; }
    .detail-row dt { color: #7a8998; }
    .detail-row dd { margin: 0; overflow-wrap: anywhere; color: #283f54; }
    .card-coordinates { border-top: 1px solid #e9eef2; padding-top: 12px;
        font-size: 10px; color: #758498; font-variant-numeric: tabular-nums; }
    .leaflet-tooltip { border: 1px solid #dce5eb; padding: 7px 10px; border-radius: 6px;
        color: #253c50; box-shadow: 0 2px 10px #17304712; font-size: 11px; }
    @media (max-width: 640px) {
        .leaflet-popup-content { max-height: calc(100dvh - 150px); overflow-y: auto; }
        .location-card { padding: 18px; }
        .leaflet-left .leaflet-control { margin-left: 12px; }
        .leaflet-right .leaflet-control { margin-right: 12px; }
        .leaflet-top .leaflet-control { margin-top: 12px; }
    }
    html, body, #root, #parent, .float-child, #map_div {
        width: 100% !important;
        height: 100% !important;
        margin: 0;
        overflow: hidden;
    }
</style>
{% endmacro %}
{% macro script(this, kwargs) %}
(function () {
    const map = {{ this._parent.get_name() }};
    let frame;
    const refreshGeometry = () => {
        map.invalidateSize({pan: false, debounceMoveend: true});
        map.eachLayer(layer => {
            if (layer instanceof L.Popup && layer.isOpen()) layer.update();
        });
    };
    // Open only after the iframe and Leaflet have their final layout dimensions.
    map.whenReady(() => requestAnimationFrame(() => requestAnimationFrame(() => {
        refreshGeometry();
        {% if this.selected_marker %}
        const selected = {{ this.selected_marker.get_name() }};
        const cluster = {{ this.cluster.get_name() }};
        const visible = cluster.getVisibleParent(selected);
        if (visible && visible !== selected && typeof visible.spiderfy === 'function') {
            cluster.once('spiderfied', () => selected.openPopup());
            visible.spiderfy();
        } else {
            selected.openPopup();
        }
        {% endif %}
    })));
    const observer = new ResizeObserver(() => {
        cancelAnimationFrame(frame);
        frame = requestAnimationFrame(refreshGeometry);
    });
    observer.observe(map.getContainer());
    map.on('unload', () => {
        observer.disconnect();
        cancelAnimationFrame(frame);
    });
})();
{% endmacro %}
""")
responsive.add_to(m)

with st.container(key="map_view"):
    st_folium(m, key="service_point_map", use_container_width=True, height=800,
              returned_objects=[], return_on_hover=False)

with st.sidebar.expander("View service point data"):
    st.dataframe(filtered, width="stretch")


if st.sidebar.button("Refresh data", icon=":material/refresh:", width="stretch"):
    st.cache_data.clear()
    st.rerun()
st.sidebar.caption("Use the filters or enter coordinates to explore the network.")