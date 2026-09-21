import re
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st


# ============================================================
# BASIC CONFIGURATION
# ============================================================

BASE_DIR = Path(__file__).parent
MASTER_FILE = BASE_DIR / "data" / "Om_Logistics_Loading_Master.xlsx"
LOGO_FILE = BASE_DIR / "assets" / "om_logo.png"

st.set_page_config(
    page_title="OM Truck Loading Optimizer",
    page_icon="🚚",
    layout="wide"
)


# ============================================================
# STYLING
# ============================================================

st.markdown(
    """
    <style>
    .main {
        background-color: #f8fafc;
    }

    .block-container {
        padding-top: 1.2rem;
        padding-bottom: 2rem;
    }

    .top-card {
        background: white;
        padding: 18px 22px;
        border-radius: 18px;
        border: 1px solid #e5e7eb;
        box-shadow: 0 4px 14px rgba(0,0,0,0.05);
        margin-bottom: 18px;
    }

    .section-card {
        background: white;
        padding: 18px;
        border-radius: 16px;
        border: 1px solid #e5e7eb;
        box-shadow: 0 2px 10px rgba(0,0,0,0.04);
        margin-bottom: 16px;
    }

    .small-muted {
        color: #6b7280;
        font-size: 0.92rem;
    }

    .success-box {
        padding: 12px;
        border-radius: 12px;
        background-color: #ecfdf5;
        color: #065f46;
        border: 1px solid #a7f3d0;
    }

    .warning-box {
        padding: 12px;
        border-radius: 12px;
        background-color: #fff7ed;
        color: #9a3412;
        border: 1px solid #fed7aa;
    }

    .error-box {
        padding: 12px;
        border-radius: 12px;
        background-color: #fef2f2;
        color: #991b1b;
        border: 1px solid #fecaca;
    }
    </style>
    """,
    unsafe_allow_html=True
)


# ============================================================
# DATA LOADING
# ============================================================

@st.cache_data
def load_master_data(master_path: Path):

    truck_df = pd.read_excel(
        master_path,
        sheet_name="Truck_Master"
    )

    docket_master_df = pd.read_excel(
        master_path,
        sheet_name="Docket_Master"
    )

    docket_items_df = pd.read_excel(
        master_path,
        sheet_name="Docket_Items"
    )

    # Clean column names
    truck_df.columns = truck_df.columns.astype(str).str.strip()
    docket_master_df.columns = docket_master_df.columns.astype(str).str.strip()
    docket_items_df.columns = docket_items_df.columns.astype(str).str.strip()

    # Standardize IDs
    truck_df["Truck_ID"] = (
        truck_df["Truck_ID"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    docket_master_df["Docket_No"] = (
        docket_master_df["Docket_No"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    docket_items_df["Docket_No"] = (
        docket_items_df["Docket_No"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    # Truck volume
    if "Truck_Volume_cuft" not in truck_df.columns:
        truck_df["Truck_Volume_cuft"] = (
            truck_df["Length_ft"]
            * truck_df["Width_ft"]
            * truck_df["Height_ft"]
        )

    # Unit volume of each physical package
    docket_items_df["Unit_Volume_cuft"] = (
        docket_items_df["Length_ft"]
        * docket_items_df["Width_ft"]
        * docket_items_df["Height_ft"]
    )

    # Total volume for each package line
    docket_items_df["Line_Total_Volume_cuft"] = (
        docket_items_df["Unit_Volume_cuft"]
        * docket_items_df["Quantity"]
    )

    # If line total weight is missing
    if "Line_Total_Weight_kg" not in docket_items_df.columns:
        docket_items_df["Line_Total_Weight_kg"] = (
            docket_items_df["Actual_Weight_kg"]
            * docket_items_df["Quantity"]
        )

    # Optional fields
    if "Stackable" not in docket_items_df.columns:
        docket_items_df["Stackable"] = "Yes"

    if "Fragile" not in docket_items_df.columns:
        docket_items_df["Fragile"] = "No"

    if "Must_Upright" not in docket_items_df.columns:
        docket_items_df["Must_Upright"] = "No"

    return truck_df, docket_master_df, docket_items_df


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def parse_docket_input(text):
    """
    Supports:
    D001
    D002
    D003

    Or:
    D001, D002, D003

    Or barcode scanner style:
    D001 D002 D003
    """
    tokens = re.split(r"[\n,; \t]+", text.strip())
    dockets = [t.strip().upper() for t in tokens if t.strip()]
    return list(dict.fromkeys(dockets))


def yes_no(value):
    return str(value).strip().lower() == "yes"

def expand_package_units(selected_items_df):
    """
    Converts package-line quantities into individual physical loading units.

    Example:
    D003 | Carton | Quantity 5

    becomes:
    D003-L1-U1
    D003-L1-U2
    D003-L1-U3
    D003-L1-U4
    D003-L1-U5
    """

    expanded_rows = []

    for _, row in selected_items_df.iterrows():

        quantity = int(row["Quantity"])

        for unit_no in range(1, quantity + 1):

            unit = row.copy()

            unit["Unit_ID"] = (
                f"{row['Docket_No']}"
                f"-L{int(row['Line_No'])}"
                f"-U{unit_no}"
            )

            unit["Unit_Number"] = unit_no

            unit["Unit_Weight_kg"] = float(
                row["Actual_Weight_kg"]
            )

            unit["Unit_Volume_cuft"] = (
                float(row["Length_ft"])
                * float(row["Width_ft"])
                * float(row["Height_ft"])
            )

            unit["Quantity"] = 1

            expanded_rows.append(unit)

    return pd.DataFrame(expanded_rows)

def get_allowed_orientations(item):

    l = float(item["Length_ft"])
    w = float(item["Width_ft"])
    h = float(item["Height_ft"])

    package_type = str(
        item["Package_Type"]
    ).strip().lower()

    must_upright = yes_no(
        item.get("Must_Upright", "No")
    )

    # Drums, pallets and crates should remain upright
    if package_type in [
        "drum",
        "pallet",
        "crate",
        "wooden crate"
    ]:
        return list(set([
            (l, w, h),
            (w, l, h)
        ]))

    # Any package explicitly marked upright
    if must_upright:
        return list(set([
            (l, w, h),
            (w, l, h)
        ]))

    # Normal carton: all reasonable rotations allowed
    return list(set([
        (l, w, h),
        (w, l, h),
        (l, h, w),
        (h, l, w),
        (w, h, l),
        (h, w, l)
    ]))

def assign_zone(priority, min_priority, max_priority):
    """
    Unload priority:
    1 = unload first
    higher number = unload later

    Loading rule:
    unload later = load first = front/deep
    unload first = load last = rear/near door
    """
    if min_priority == max_priority:
        return "Full Truck / Balanced"

    if priority == min_priority:
        return "Rear / Near Door"

    if priority == max_priority:
        return "Front / Deep Inside"

    return "Middle Zone"


def get_zone_range(zone, truck_length):
    one_third = truck_length / 3

    zone_map = {
        "Front / Deep Inside": (0, one_third),
        "Middle Zone": (one_third, 2 * one_third),
        "Rear / Near Door": (2 * one_third, truck_length),
        "Full Truck / Balanced": (0, truck_length)
    }

    return zone_map.get(zone, (0, truck_length))


def interval_overlap(a_start, a_end, b_start, b_end):
    return max(a_start, b_start) < min(a_end, b_end)


def boxes_overlap(a, b):
    x_overlap = interval_overlap(a["x"], a["x"] + a["l"], b["x"], b["x"] + b["l"])
    y_overlap = interval_overlap(a["y"], a["y"] + a["w"], b["y"], b["y"] + b["w"])
    z_overlap = interval_overlap(a["z"], a["z"] + a["h"], b["z"], b["z"] + b["h"])
    return x_overlap and y_overlap and z_overlap


def xy_overlap(a, b):
    x_overlap = interval_overlap(a["x"], a["x"] + a["l"], b["x"], b["x"] + b["l"])
    y_overlap = interval_overlap(a["y"], a["y"] + a["w"], b["y"], b["y"] + b["w"])
    return x_overlap and y_overlap


def support_is_allowed(candidate, placed_boxes):
    """
    If box is on floor, allowed.
    If box is above floor, it must sit on boxes that are stackable and not fragile.
    This is simplified prototype logic.
    """
    if candidate["z"] == 0:
        return True

    support_found = False

    for box in placed_boxes:
        top_of_box = box["z"] + box["h"]

        if abs(top_of_box - candidate["z"]) < 0.001 and xy_overlap(candidate, box):
            support_found = True

            if box["Stackable"] == "No":
                return False

            if box["Fragile"] == "Yes":
                return False

    return support_found


def build_candidate_positions(placed_boxes, zone_start):
    x_candidates = {round(zone_start, 3)}
    y_candidates = {0}
    z_candidates = {0}

    for box in placed_boxes:
        x_candidates.add(round(box["x"] + box["l"], 3))
        y_candidates.add(round(box["y"] + box["w"], 3))
        z_candidates.add(round(box["z"] + box["h"], 3))

    candidates = []

    for z in sorted(z_candidates):
        for x in sorted(x_candidates):
            for y in sorted(y_candidates):
                candidates.append((x, y, z))

    return candidates


def find_position_for_box(item, placed_boxes, truck, preferred_zone):
    truck_length = float(truck["Length_ft"])
    truck_width = float(truck["Width_ft"])
    truck_height = float(truck["Height_ft"])

    preferred_zones = [
        preferred_zone,
        "Front / Deep Inside",
        "Middle Zone",
        "Rear / Near Door",
        "Full Truck / Balanced"
    ]

    seen = set()
    zones_to_try = []

    for zone in preferred_zones:
        if zone not in seen:
            seen.add(zone)
            zones_to_try.append(zone)

    orientations = get_allowed_orientations(item)

    for zone in zones_to_try:
        zone_start, zone_end = get_zone_range(zone, truck_length)

        for l, w, h in orientations:
            candidate_positions = build_candidate_positions(placed_boxes, zone_start)

            for x, y, z in candidate_positions:
                candidate = {
                    "x": x,
                    "y": y,
                    "z": z,
                    "l": l,
                    "w": w,
                    "h": h,
                    "Stackable": item["Stackable"],
                    "Fragile": item["Fragile"]
                }

                if x < zone_start:
                    continue

                if x + l > zone_end:
                    continue

                if y + w > truck_width:
                    continue

                if z + h > truck_height:
                    continue

                collision = any(boxes_overlap(candidate, box) for box in placed_boxes)

                if collision:
                    continue

                if not support_is_allowed(candidate, placed_boxes):
                    continue

                return {
                    "x": x,
                    "y": y,
                    "z": z,
                    "l": l,
                    "w": w,
                    "h": h,
                    "Actual_Zone_Used": zone
                }

    return None


def create_loading_plan(selected_items_df, priority_df, truck):

    # Add unloading priority to every package line
    working_df = selected_items_df.merge(
        priority_df,
        on="Docket_No",
        how="left"
    )

    # Expand quantities into individual physical packages
    final_df = expand_package_units(working_df)

    min_priority = int(
        final_df["Unload_Priority"].min()
    )

    max_priority = int(
        final_df["Unload_Priority"].max()
    )

    final_df["Preferred_Zone"] = (
        final_df["Unload_Priority"]
        .apply(
            lambda p: assign_zone(
                int(p),
                min_priority,
                max_priority
            )
        )
    )

    # Sorting logic
    # Higher priority number = unload later
    # therefore load earlier / deeper inside

    final_df["Stackable_Sort"] = (
        final_df["Stackable"]
        .apply(
            lambda x: 1
            if str(x).strip().lower() == "no"
            else 0
        )
    )

    final_df["Fragile_Sort"] = (
        final_df["Fragile"]
        .apply(
            lambda x: 1
            if str(x).strip().lower() == "yes"
            else 0
        )
    )

    final_df = final_df.sort_values(
        by=[
            "Unload_Priority",
            "Stackable_Sort",
            "Fragile_Sort",
            "Unit_Weight_kg",
            "Unit_Volume_cuft"
        ],
        ascending=[
            False,
            False,
            True,
            False,
            False
        ]
    ).reset_index(drop=True)

    final_df["Loading_Order"] = range(
        1,
        len(final_df) + 1
    )

    placed_boxes = []
    unplaced_rows = []

    for _, row in final_df.iterrows():

        position = find_position_for_box(
            row,
            placed_boxes,
            truck,
            row["Preferred_Zone"]
        )

        if position is None:

            unplaced_rows.append(
                row["Unit_ID"]
            )

            continue

        warning_notes = []

        if yes_no(row["Fragile"]):
            warning_notes.append(
                "Fragile: avoid heavy stacking"
            )

        if not yes_no(row["Stackable"]):
            warning_notes.append(
                "Non-stackable: floor preference"
            )

        if (
            row["Preferred_Zone"]
            != position["Actual_Zone_Used"]
        ):
            warning_notes.append(
                "Placed outside preferred zone due to fit constraints"
            )

        placed_box = {

            "Unit_ID": row["Unit_ID"],

            "Docket_No": row["Docket_No"],

            "Line_No": int(row["Line_No"]),

            "Package_Type": row["Package_Type"],

            "Unload_Priority": int(
                row["Unload_Priority"]
            ),

            "Loading_Order": int(
                row["Loading_Order"]
            ),

            "Preferred_Zone": row[
                "Preferred_Zone"
            ],

            "Actual_Zone_Used": position[
                "Actual_Zone_Used"
            ],

            "x": position["x"],
            "y": position["y"],
            "z": position["z"],

            "l": position["l"],
            "w": position["w"],
            "h": position["h"],

            "Weight_kg": float(
                row["Unit_Weight_kg"]
            ),

            "Volume_cuft": float(
                row["Unit_Volume_cuft"]
            ),

            "Stackable": row["Stackable"],

            "Fragile": row["Fragile"],

            "Must_Upright": row[
                "Must_Upright"
            ],

            "Warning_Note":
                "; ".join(warning_notes)
                if warning_notes
                else "OK"
        }

        placed_boxes.append(
            placed_box
        )

    placement_df = pd.DataFrame(
        placed_boxes
    )

    return (
        final_df,
        placement_df,
        unplaced_rows
    )

def create_truck_3d_figure(placement_df, truck):
    truck_length = float(truck["Length_ft"])
    truck_width = float(truck["Width_ft"])
    truck_height = float(truck["Height_ft"])

    fig = go.Figure()

    # Truck outline
    corners = [
        (0, 0, 0),
        (truck_length, 0, 0),
        (truck_length, truck_width, 0),
        (0, truck_width, 0),
        (0, 0, truck_height),
        (truck_length, 0, truck_height),
        (truck_length, truck_width, truck_height),
        (0, truck_width, truck_height)
    ]

    edges = [
        (0, 1), (1, 2), (2, 3), (3, 0),
        (4, 5), (5, 6), (6, 7), (7, 4),
        (0, 4), (1, 5), (2, 6), (3, 7)
    ]

    for edge in edges:
        x_vals = [corners[edge[0]][0], corners[edge[1]][0]]
        y_vals = [corners[edge[0]][1], corners[edge[1]][1]]
        z_vals = [corners[edge[0]][2], corners[edge[1]][2]]

        fig.add_trace(
            go.Scatter3d(
                x=x_vals,
                y=y_vals,
                z=z_vals,
                mode="lines",
                line=dict(width=4),
                showlegend=False
            )
        )

    # Zone divider lines
    for x_div in [truck_length / 3, 2 * truck_length / 3]:
        fig.add_trace(
            go.Scatter3d(
                x=[x_div, x_div, x_div, x_div, x_div],
                y=[0, truck_width, truck_width, 0, 0],
                z=[0, 0, truck_height, truck_height, 0],
                mode="lines",
                line=dict(width=3, dash="dash"),
                showlegend=False
            )
        )

    # Add each docket as a 3D cuboid
    color_list = [
        "#2563eb", "#16a34a", "#dc2626", "#9333ea", "#ea580c",
        "#0891b2", "#65a30d", "#be123c", "#7c3aed", "#ca8a04"
    ]
    unique_dockets = list(
        placement_df["Docket_No"].unique()
    )

    docket_color_map = {
        docket: color_list[
            i % len(color_list)
        ]
        for i, docket
        in enumerate(unique_dockets)
    }

    for idx, row in placement_df.iterrows():
        x0, y0, z0 = row["x"], row["y"], row["z"]
        x1, y1, z1 = x0 + row["l"], y0 + row["w"], z0 + row["h"]

        vertices = [
            (x0, y0, z0),
            (x1, y0, z0),
            (x1, y1, z0),
            (x0, y1, z0),
            (x0, y0, z1),
            (x1, y0, z1),
            (x1, y1, z1),
            (x0, y1, z1)
        ]

        x = [v[0] for v in vertices]
        y = [v[1] for v in vertices]
        z = [v[2] for v in vertices]

        i = [0, 0, 0, 1, 1, 2, 4, 4, 5, 6, 3, 7]
        j = [1, 2, 4, 2, 5, 3, 5, 6, 6, 7, 7, 4]
        k = [2, 3, 5, 5, 6, 7, 6, 7, 1, 2, 0, 0]

        fig.add_trace(
            go.Mesh3d(
                x=x,
                y=y,
                z=z,
                i=i,
                j=j,
                k=k,
                opacity=0.65,
                color=docket_color_map[
                    row["Docket_No"]
                ],
                name=str(row["Docket_No"]),
                hovertext=(
                    f"<b>Docket: {row['Docket_No']}</b><br>"
                    f"Unit: {row['Unit_ID']}<br>"
                    f"Package: {row['Package_Type']}<br>"
                    f"Dimensions: "
                    f"{row['l']:.2f} × "
                    f"{row['w']:.2f} × "
                    f"{row['h']:.2f} ft<br>"
                    f"Weight: {row['Weight_kg']:.1f} kg<br>"
                    f"Unload priority: {row['Unload_Priority']}<br>"
                    f"Loading order: {row['Loading_Order']}<br>"
                    f"Zone: {row['Actual_Zone_Used']}<br>"
                    f"Stackable: {row['Stackable']}<br>"
                    f"Fragile: {row['Fragile']}"
                ),
                hoverinfo="text",
                showlegend=False
            )
        )

    for docket, color in docket_color_map.items():
        fig.add_trace(
            go.Scatter3d(
                x=[None],
                y=[None],
                z=[None],
                mode="markers",
                marker=dict(
                    size=10,
                    color=color
                ),
                name=docket,
                showlegend=True
            )
        )

    fig.add_annotation(
        text="Front / Deep Inside",
        x=0.10,
        y=1.04,
        xref="paper",
        yref="paper",
        showarrow=False
    )

    fig.add_annotation(
        text="Rear Door / Unloading Side",
        x=0.88,
        y=1.04,
        xref="paper",
        yref="paper",
        showarrow=False
    )

    fig.update_layout(
        height=720,
        margin=dict(l=0, r=0, t=45, b=0),
        scene=dict(
            xaxis_title="Truck length: front to rear",
            yaxis_title="Truck width",
            zaxis_title="Truck height",
            xaxis=dict(range=[0, truck_length]),
            yaxis=dict(range=[0, truck_width]),
            zaxis=dict(range=[0, truck_height]),
            aspectmode="manual",
            aspectratio=dict(
                x=max(truck_length / truck_width, 1),
                y=1,
                z=max(truck_height / truck_width, 0.7)
            )
        ),
        title="3D Virtual Truck Loading Layout"
    )

    return fig


# ============================================================
# HEADER
# ============================================================

st.markdown('<div class="top-card">', unsafe_allow_html=True)

header_col1, header_col2 = st.columns([1, 5])

with header_col1:
    if LOGO_FILE.exists():
        st.image(str(LOGO_FILE), width=140)
    else:
        st.markdown("### OM Logistics")
        st.caption("Logo placeholder")

with header_col2:
    st.title("AI-Assisted Truck Loading Optimizer")
    st.markdown(
        """
        <div class="small-muted">
        Stage 1 prototype for docket-based truck space optimization.
        User enters only truck ID, selected docket numbers, and unloading priority.
        The system automatically extracts all truck and docket details from the master Excel file.
        </div>
        """,
        unsafe_allow_html=True
    )


# ============================================================
# MASTER DATA LOAD
# ============================================================

if not MASTER_FILE.exists():
    st.error(
        "Master Excel file not found. Run create_sample_excel.py first."
    )
    st.code("python create_sample_excel.py")
    st.stop()

truck_df, docket_master_df, docket_items_df = load_master_data(MASTER_FILE)


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:
    st.header("System Status")
    st.success("Master Excel loaded automatically")

    st.write("Master file:")
    st.code(str(MASTER_FILE.name))

    st.divider()

    st.subheader("Available Trucks")
    st.dataframe(
        truck_df[[
            "Truck_ID",
            "Truck_Type",
            "Length_ft",
            "Width_ft",
            "Height_ft",
            "Max_Weight_kg",
            "Truck_Volume_cuft"
        ]],
        hide_index=True,
        width='stretch'
    )


# ============================================================
# MAIN INPUT SECTION
# ============================================================

st.markdown('<div class="section-card">', unsafe_allow_html=True)
st.subheader("1. Select Truck")

truck_id = st.selectbox(
    "Select truck ID",
    truck_df["Truck_ID"].tolist()
)

truck = truck_df[truck_df["Truck_ID"] == truck_id].iloc[0]

truck_col1, truck_col2, truck_col3, truck_col4 = st.columns(4)

truck_col1.metric("Truck type", truck["Truck_Type"])
truck_col2.metric("Max weight", f"{truck['Max_Weight_kg']:,.0f} kg")
truck_col3.metric("Truck volume", f"{truck['Truck_Volume_cuft']:,.1f} cu.ft.")
truck_col4.metric("Dimensions", f"{truck['Length_ft']} × {truck['Width_ft']} × {truck['Height_ft']} ft")



# st.markdown('<div class="section-card">', unsafe_allow_html=True)
st.subheader("2. Enter Selected Docket Numbers")

st.caption(
    "Enter docket numbers selected by the manager. "
    "You can type one per line, comma separated, or paste barcode-scanner output."
)

docket_text = st.text_area(
    "Docket numbers",
    # value="D001\nD002\nD003\nD004\nD005\nD008",
    height=150
)

selected_dockets = parse_docket_input(docket_text)

matched_df = docket_master_df[docket_master_df["Docket_No"].isin(selected_dockets)].copy()
selected_items_df = docket_items_df[
    docket_items_df["Docket_No"].isin(selected_dockets)
].copy()
missing_dockets = [d for d in selected_dockets if d not in matched_df["Docket_No"].tolist()]

if missing_dockets:
    st.warning(f"These docket numbers were not found in Docket_Master: {', '.join(missing_dockets)}")

if matched_df.empty:
    st.error("No valid dockets selected.")
    st.stop()

st.write("Extracted docket details from master Excel:")
st.dataframe(matched_df, hide_index=True, width='stretch')
with st.expander("Show package details inside selected dockets"):
    st.dataframe(
        selected_items_df,
        hide_index=True,
        width="stretch"
    )

# st.markdown('</div>', unsafe_allow_html=True)


# st.markdown('<div class="section-card">', unsafe_allow_html=True)
st.subheader("3. Enter Unloading Priority")

st.caption(
    "Priority 1 means unload first. "
    "Higher number means unload later. "
    "The tool will load later-unloading items first and place them deeper inside."
)

default_priority = pd.DataFrame({
    "Docket_No": matched_df["Docket_No"].tolist(),
    "Unload_Priority": list(range(1, len(matched_df) + 1))
})

priority_df = st.data_editor(
    default_priority,
    hide_index=True,
    width='stretch',
    column_config={
        "Docket_No": st.column_config.TextColumn(
            "Docket No.",
            disabled=True
        ),
        "Unload_Priority": st.column_config.NumberColumn(
            "Unload priority",
            min_value=1,
            step=1
        )
    }
)

if priority_df["Unload_Priority"].isna().any():
    st.error("Please enter unloading priority for every docket.")
    st.stop()

priority_df["Unload_Priority"] = priority_df["Unload_Priority"].astype(int)

st.markdown('</div>', unsafe_allow_html=True)


# ============================================================
# OPTIMIZATION BUTTON
# ============================================================

generate = st.button("Generate Loading Plan", type="primary", width='stretch')

if generate:
    final_df, placement_df, unplaced_rows = create_loading_plan(
        selected_items_df,
        priority_df,
        truck
    )

    total_weight = final_df[
        "Unit_Weight_kg"
    ].sum()

    total_volume = final_df[
        "Unit_Volume_cuft"
    ].sum()

    truck_weight = float(truck["Max_Weight_kg"])
    truck_volume = float(truck["Truck_Volume_cuft"])

    weight_utilization = (total_weight / truck_weight) * 100
    volume_utilization = (total_volume / truck_volume) * 100

    unused_weight = max(
        truck_weight - total_weight,
        0
    )

    unused_volume = max(
        truck_volume - total_volume,
        0
    )

    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.subheader("4. Loading Feasibility Dashboard")

    kpi1, kpi2, kpi3, kpi4 = st.columns(4)

    kpi1.metric("Weight utilization", f"{weight_utilization:.1f}%")
    kpi2.metric("Volume utilization", f"{volume_utilization:.1f}%")
    kpi3.metric("Unused weight", f"{unused_weight:,.0f} kg")
    kpi4.metric("Unused volume", f"{unused_volume:,.1f} cu.ft.")

    warnings = []

    if total_weight > truck_weight:
        warnings.append("Total weight exceeds truck permissible capacity.")

    if total_volume > truck_volume:
        warnings.append("Total volume exceeds truck internal volume.")

    if unplaced_rows:
        warnings.append(
            f"Could not place these package units in the 3D layout: "
            f"{', '.join(unplaced_rows)}"
        )

    if warnings:
        st.markdown(
            f"""
            <div class="warning-box">
            <b>Warning:</b><br>{'<br>'.join(warnings)}
            </div>
            """,
            unsafe_allow_html=True
        )
    else:
        st.markdown(
            """
            <div class="success-box">
            <b>Feasible:</b> Selected dockets fit within available weight and volume limits in this prototype run.
            </div>
            """,
            unsafe_allow_html=True
        )

    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.subheader("5. Recommended Loading Plan")

    if not placement_df.empty:
        output_cols = [
            "Loading_Order",
            "Unit_ID",
            "Docket_No",
            "Package_Type",
            "Unload_Priority",
            "Preferred_Zone",
            "Actual_Zone_Used",
            "Weight_kg",
            "Volume_cuft",
            "Stackable",
            "Fragile",
            "Must_Upright",
            "Warning_Note"
        ]

        st.dataframe(
            placement_df[output_cols].sort_values("Loading_Order"),
            hide_index=True,
            width='stretch'
        )

        csv_data = placement_df[output_cols].sort_values("Loading_Order").to_csv(index=False).encode("utf-8")

        st.download_button(
            label="Download Loading Plan CSV",
            data=csv_data,
            file_name="loading_plan.csv",
            mime="text/csv"
        )
    else:
        st.error("No docket could be placed. Check truck size and docket dimensions.")

    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.subheader("6. AI Explanation / Decision Notes")

    explanation = f"""
    The tool selected truck {truck_id} ({truck['Truck_Type']}) and extracted docket details automatically from the master Excel file.
    The total selected docket weight is {total_weight:,.0f} kg against a permissible capacity of {truck_weight:,.0f} kg.
    The total selected docket volume is {total_volume:,.1f} cu.ft. against an internal truck volume of {truck_volume:,.1f} cu.ft.

    Loading logic used:
    - Dockets with higher unloading priority numbers are unloaded later, so they are loaded first and placed deeper inside the truck.
    - Dockets with priority 1 are unloaded first, so they are loaded last and placed near the rear door.
    - Heavy and non-stackable items are given floor preference.
    - Fragile items are flagged so loading staff avoid heavy stacking over them.
    - The 3D layout is a prototype-level visual guide and must be reviewed by the operations supervisor before actual loading.
    """

    st.info(explanation)

    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.subheader("7. 3D Virtual Truck Layout")

    if not placement_df.empty:
        fig = create_truck_3d_figure(placement_df, truck)
        st.plotly_chart(fig, width='stretch')

        with st.expander("Show 3D coordinate table"):
            coord_cols = [
                "Unit_ID",
                "Docket_No",
                "Package_Type",
                "Unload_Priority",
                "x",
                "y",
                "z",
                "l",
                "w",
                "h",
                "Actual_Zone_Used",
                "Loading_Order"
            ]

            st.dataframe(
                placement_df[coord_cols].sort_values("Loading_Order"),
                hide_index=True,
                width='stretch'
            )
    else:
        st.warning("3D layout cannot be shown because no boxes were placed.")

    st.markdown('</div>', unsafe_allow_html=True)

else:
    st.info("Enter truck ID, docket numbers, and unloading priority. Then click Generate Loading Plan.")