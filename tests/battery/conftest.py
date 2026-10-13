"""Synthetic fixtures. No customer data is ever committed; these files are written
to tmp_path at test time and mirror pathologies common in CMMS work-order
exports."""
from __future__ import annotations

from pathlib import Path

import pytest

from warrant.battery.gloss.source import SourceTable, open_workspace

# Columns chosen so that all seven detectors have something to find. PCACTHRS is
# present because the dictionary documents it as a computed field, which is what
# the RULE detector reads.
_HEADER = (
    "WORKORDERID,WOCLASS,ISTASK,PARENT,DESCRIPTION,STATUS,WORKTYPE,"
    "WOPRIORITY,SCHEDSTART,REPORTDATE,ACTSTART,ASSETNUM,LOCATION,OWNERGROUP,"
    "PCACTHRS"
)

# 20 rows. Deterministic, and every expected value in the detector tests is
# derived from this literal block by hand.
_ROWS = [
    "1,WORKORDER,0,,AHU FAN IN ALARM,CLOSE,CM,1,01-AUG-23,01-AUG-23,02-AUG-23,A100,X101,,100",
    "2,WORKORDER,0,,TRIPPED CIRCUIT,CLOSE,CM,1,02-AUG-23,02-AUG-23,03-AUG-23,,X101,,100",
    "3,WORKORDER,0,,PEST CONTROL ROUNDS,CLOSE,CM,6,03-AUG-23,03-AUG-23,01-NOV-23,,GARAGE,,50",
    "4,WORKORDER,0,,JANITORIAL,CLOSE,CM,6,04-AUG-23,04-AUG-23,02-NOV-23,,SHOPS,,50",
    "5,WORKORDER,0,,ANNUAL FIRE ALARM INSPECTION,CLOSE,PM,5,05-AUG-23,05-AUG-23,16-SEP-23,A100,X101,,100",
    "6,WORKORDER,0,,QUARTERLY FILTER CHANGE,CLOSE,PM,5,06-AUG-23,06-AUG-23,17-SEP-23,A200,X102,,100",
    "7,WORKORDER,0,,ROUTE CHECK CHILLER,CLOSE,RCHK,5,07-AUG-23,07-AUG-23,18-SEP-23,A200,X102,,100",
    "8,WORKORDER,0,,ROUTE CHECK BOILER,CLOSE,RCHK,5,08-AUG-23,08-AUG-23,19-SEP-23,A300,X102,,100",
    "9,WORKORDER,0,,SAFETY WALKTHROUGH,COMP,SWK,3,09-AUG-23,09-AUG-23,10-AUG-23,A300,SHOPS,,0",
    "10,WORKORDER,0,,NOTIFY\xa0FRONT\xa0DESK,CLOSE,CM,1,10-AUG-23,10-AUG-23,11-AUG-23,A100,X101,,100",
    "11,ACTIVITY,1,1,AHU FAN IN ALARM - STEP 1,CLOSE,CM,1,01-AUG-23,01-AUG-23,02-AUG-23,A100,X101,,100",
    "12,ACTIVITY,1,1,AHU FAN IN ALARM - STEP 2,CLOSE,CM,1,01-AUG-23,01-AUG-23,02-AUG-23,A100,X101,,100",
    "13,ACTIVITY,1,5,FIRE ALARM - PANEL,CLOSE,PM,5,05-AUG-23,05-AUG-23,16-SEP-23,A100,X101,,100",
    "14,ACTIVITY,1,5,FIRE ALARM - DEVICES,CLOSE,PM,5,05-AUG-23,05-AUG-23,16-SEP-23,A100,X101,,100",
    "15,ACTIVITY,1,6,FILTER CHANGE - AHU1,CLOSE,PM,5,06-AUG-23,06-AUG-23,17-SEP-23,A200,X102,,100",
    "16,ACTIVITY,1,7,ROUTE CHECK CHILLER - CH1,CLOSE,RCHK,5,07-AUG-23,07-AUG-23,18-SEP-23,A200,X102,,100",
    "17,ACTIVITY,1,7,ROUTE CHECK CHILLER - CH2,CLOSE,RCHK,5,07-AUG-23,07-AUG-23,18-SEP-23,A200,X102,,100",
    "18,ACTIVITY,1,8,ROUTE CHECK BOILER - B1,CLOSE,RCHK,5,08-AUG-23,08-AUG-23,19-SEP-23,A300,X102,,100",
    "19,ACTIVITY,1,3,PEST CONTROL - FLOOR 1,CLOSE,CM,6,03-AUG-23,03-AUG-23,01-NOV-23,,GARAGE,,50",
    "20,ACTIVITY,1,4,JANITORIAL - FLOOR 2,CLOSE,CM,6,04-AUG-23,04-AUG-23,02-NOV-23,,SHOPS,,50",
]

# assetnum A400 is absent from the work-order table, which exercises reverse
# coverage in the LINK detector.
_ASSETS = [
    "assetnum,description,location,parent",
    "A100,\"Pump\",X101,P1",
    "A200,\"Pump, CIRCULATING\",X102,P2",
    "A300,\"Pump, SUMP\",X102,P9",
    "A400,\"Pump, BOOSTER\",X102,P2",
]

# Shaped like a commercial CMMS attribute-dictionary export: declared types plus
# REMARKS that contradict the data. The REMARKS text is invented for this fixture.
_DICT = [
    "OBJECTNAME,ATTRIBUTENAME,MAXTYPE,TITLE,REMARKS",
    'WORKORDER,WOPRIORITY,INTEGER,Priority,"Relative urgency of the job, on a scale '
    'from 0-100, where 0 is the lowest priority and 100 is the highest."',
    'WORKORDER,SCHEDSTART,DATETIME,Scheduled Start,"When the job is planned to '
    'start, to the minute."',
    'WORKORDER,WORKTYPE,UPPER,Work Type,"Category of the job, for instance planned '
    'upkeep or a repair after a breakdown."',
    'WORKORDER,ISTASK,YORN,Is Task,"Flags a record that is a step of a larger job."',
    'WORKORDER,WOCLASS,UPPER,Class,"Kind of record this row holds."',
    'WORKORDER,ASSETNUM,UPPER,Asset,"Equipment the job was done on."',
    'WORKORDER,LOCATION,UPPER,Location,"Place where the job was done."',
    'WORKORDER,PCACTHRS,DECIMAL,Pct Complete,"Share of the job finished, calculated '
    'from hours booked so far against the hours estimated."',
    'WORKORDER,STATUS,UPPER,Status,"Where the job stands in its life cycle."',
]

_COSTS = [
    "WONUM,ACTLABCOST,ACTMATCOST,ACTTOTALCOST",
    "1,100.00,0.00,100.00",
    "2,50.00,25.00,75.00",
    "3,10.00,5.00,15.00",
    "4,20.00,0.00,20.00",
    "5,30.00,0.00,31.50",   # a third component this export does not carry
]


@pytest.fixture
def mini_paths(tmp_path: Path) -> dict[str, Path]:
    """Writes the work-order table in cp1252 (as many legacy exports are) and the
    supporting files in UTF-8."""
    wo = tmp_path / "mini_wo.csv"
    wo.write_bytes(("\n".join([_HEADER, *_ROWS]) + "\n").encode("cp1252"))
    assets = tmp_path / "mini_assets.csv"
    assets.write_text("\n".join(_ASSETS) + "\n", encoding="utf-8")
    dictionary = tmp_path / "mini_dict.csv"
    dictionary.write_text("\n".join(_DICT) + "\n", encoding="utf-8")
    return {"wo": wo, "assets": assets, "dict": dictionary}


@pytest.fixture
def mini_conn(mini_paths, tmp_path):
    """A workspace with wo_history and assets registered under logical names."""
    return open_workspace(
        [SourceTable(name="wo_history", path=mini_paths["wo"], encoding="cp1252"),
         SourceTable(name="assets", path=mini_paths["assets"], encoding="utf-8")],
        cache_dir=tmp_path / "cache",
    )


@pytest.fixture
def costs_conn(tmp_path):
    p = tmp_path / "mini_costs.csv"
    p.write_text("\n".join(_COSTS) + "\n", encoding="utf-8")
    return open_workspace([SourceTable(name="costs", path=p, encoding="utf-8")],
                          cache_dir=tmp_path / "cache")
