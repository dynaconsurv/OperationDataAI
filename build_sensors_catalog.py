"""Script to populate config/sensors.json from the user's provided AF attributes table."""

import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
CONFIG_DIR = BASE_DIR / "config"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)

RAW_TABLE = r"""
MALAYSIA\BORF\GTG\GT-2420A\Air Filter System\Ambient Inlet Pressure	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Air Filter System\Hi Differential Pressure Fine Filter	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Air Filter System\Hi Differential Pressure HEPA 1	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Air Filter System\Hi Differential Pressure Prefilter	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Compressor\Journal Bearing Temperature 1	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Compressor\Journal Bearing Temperature 2	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Compressor\Journal Bearing Temperature 3	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Compressor\Journal Bearing Temperature 4	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Compressor\Shaft Axial Display A	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Compressor\Shaft Axial Display B	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Compressor\Shaft X Radial Vibrationration 1	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Compressor\Shaft X Radial Vibrationration 2	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Compressor\Shaft Y Radial Vibrationration 1	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Compressor\Shaft Y Radial Vibrationration 2	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Compressor\Thrust Bearing Active Side Temperature1	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Compressor\Thrust Bearing Non-Active Side Temperature1	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Compressor Process\1st Inlet Flow	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Compressor Process\1st Stage ASV	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Compressor Process\1st Stage Inlet Pressure	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Compressor Process\1st Stage Inlet Temperature	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Compressor Process\1st Stage Outlet Pressure	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Compressor Process\1st Stage Outlet Temperature	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Compressor Process\1st Stage Ratio	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Compressor Process\2nd Stage ASV	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Compressor Process\2nd Stage Inlet Flow	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Compressor Process\2nd Stage Inlet Pressure	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Compressor Process\2nd Stage Inlet Temperature	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Compressor Process\2nd Stage Outlet Pressure	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Compressor Process\2nd Stage Outlet Temperature	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Compressor Process\2nd Stage Ratio	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Compressor Process\ASV Position Transmitter	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Compressor Process\ASV Position Transmitter 2	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Compressor Process\Comp. Suction Pressure.	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Dry Gas Seal System\Buff Seal Gas Inlet Pos.	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Dry Gas Seal System\DE CC Vent Pressure	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Dry Gas Seal System\DE Primary Vent Flow	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Dry Gas Seal System\Differential Pressure Seal Gas Amplifier	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Dry Gas Seal System\Differential Pressure Seal Gas Filter	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Dry Gas Seal System\N2 Filter Differential Pressure	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Dry Gas Seal System\Primary Vent Pressure 1	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Dry Gas Seal System\Primary Vent Pressure 2	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Dry Gas Seal System\Primary Vent Pressure 3	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Dry Gas Seal System\Primary Vent Pressure 4	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Dry Gas Seal System\Primary Vent Pressure 5	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Dry Gas Seal System\Primary Vent Pressure 6	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Dry Gas Seal System\SE CC Vent Pressure	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Dry Gas Seal System\SE Primary Vent Flow	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Dry Gas Seal System\Seal Gas Balancing Pressure 1	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Dry Gas Seal System\Seal Gas Balancing Pressure 2	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Dry Gas Seal System\Seal Gas Heater Temperature 1	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Dry Gas Seal System\Seal Gas Heater Temperature 2	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Dry Gas Seal System\Seal Gas Heater Temperature 3	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Dry Gas Seal System\Tertiary Seal Gas Pressure	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Dry Gas Seal System\Tertiary Seal Gas Pressure  2	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Dry Gas Seal System\Tertiary Seal Gas Pressure 1	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Dry Gas Seal System\Tertiary Seal Gas Pressure 3	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Enclosure System\Couple Internal Temperature 2	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Enclosure System\Gas Detector Acc Vent Out 1	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Enclosure System\Gas Detector GT Vent Outlet	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Enclosure System\Gas Detector Inlet Filter 1	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Enclosure System\Turbine Internal Temperature 1	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Enclosure System\Turbine Internal Temperature 2	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Enclosure System\Turbine Internal Temperature 3	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Enclosure System\Turbine Vent Pressure 1	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Enclosure System\Turbine Vent Pressure 2	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Enclosure System\Turbine Vent Pressure 3	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Fuel Gas System\Fuel Gas  SSRV 1	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Fuel Gas System\Fuel Gas  Upstream Valve Pressure	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Fuel Gas System\Fuel Gas Control Valve 1	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Fuel Gas System\Fuel Gas Inlet Pressure 1	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Fuel Gas System\Fuel Gas Inlet Temperature	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Fuel Gas System\Fuel Gas Interstage Pressure 1	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Fuel Gas System\Fuel Gas Interstage Pressure 2	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Fuel Gas System\Fuel Gas Interstage Pressure 3	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Average Axial Discharge Pressure	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Average Exhaust Temperature	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Axial Discharge Pressure 1	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Axial Discharge Pressure 2	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Axial Discharge Pressure 3	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Axial Discharge Temperature 1	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Axial Discharge Temperature 2	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Axial Inlet Temperature 1	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Axial Inlet Temperature 2	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Drain Temperature Journal Bearing 1	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Drain Temperature Journal Bearing 2	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Drain Temperature Journal Bearing 3	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Drain Temperature Journal Thrust Bearing 4	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Drain Temperature Thrust Bearing 1	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Exhaust Back Pressure	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Exhaust Temperature 1	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Exhaust Temperature 10	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Exhaust Temperature 11	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Exhaust Temperature 12	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Exhaust Temperature 13	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Exhaust Temperature 2	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Exhaust Temperature 3	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Exhaust Temperature 4	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Exhaust Temperature 5	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Exhaust Temperature 6	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Exhaust Temperature 7	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Exhaust Temperature 8	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Exhaust Temperature 9	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Flame Detector 10	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Flame Detector 11	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Flame Detector 2	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Flame Detector 3	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\HP Axial 1	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\HP Axial 2	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\HP Shaft Control 1	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\HP Shaft Speed 1	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\HP Vibration 1	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\IGV 2	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Journal Brg 4 Temperature 1	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\LP Axial 1	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\LP Axial 2	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\LP Shaft Control 1	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\LP Shaft Pick Up 1	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\LP Vibration 1	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Spread Exhaust Temperature	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Stage 1 WS AFT Inner Temperature 1	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Stage 1 WS FWD Inner Temperature 1	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Stage 2 Nozzle 2	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Stage 2 WS AFT Inner Temperature 1	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Stage 2 WS FWD Inner Temperature 1	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Thrust Bearing 4 Active Temperature	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Thrust Bearing 4 Inactive Temperature	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Turbine Bearing 1 Radial Vibration 1	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Turbine Bearing 4 Radial Vibration 1	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Gearbox\Gearbox DE Pinion Brg X Vibration	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Gearbox\Gearbox DE Pinion Brg Y Vibration	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Gearbox\Gearbox DE Pinion Journal Brg 2	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Gearbox\Gearbox DE Wheel Brg X Vibration	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Gearbox\Gearbox DE Wheel Brg Y Vibration	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Gearbox\Gearbox DE Wheel Journal Brg Temperature 1	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Gearbox\Gearbox DE Wheel Journal Brg Temperature 2	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Gearbox\Gearbox NDE Pinion Brg X Vibration	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Gearbox\Gearbox NDE Pinion Brg Y Vibration	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Gearbox\Gearbox NDE Pinion Journal Brg Temperature 2	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Gearbox\Gearbox NDE Wheel Brg X Vibration	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Gearbox\Gearbox NDE Wheel Brg Y Vibration	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Gearbox\Gearbox NDE Wheel Journal Brg Temperature 1	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Gearbox\Gearbox NDE Wheel Journal Brg Temperature 2	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Gearbox\Gearbox Wheel Axial 1	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Gearbox\Gearbox Wheel Axial 2	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Gearbox\Gearbox Wheel Casing	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Gearbox\Gearbox Wheel Thrust Bearing Active Temperature 1	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Gearbox\Gearbox Wheel Thrust Bearing Active Temperature 2	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Gearbox\Gearbox Wheel Thrust Bearing Inactive Temperature 1	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Gearbox\Gearbox Wheel Thrust Bearing Inactive Temperature 2	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Hydraulic System\Control Oil Header Pressure 1	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Hydraulic System\Control Oil Header Pressure 2	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Hydraulic System\Control Oil Header Pressure 3	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Hydraulic System\Differential Pressure Hydraulic Filter	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Hydraulic System\Hydraulic Header Pressure	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Lube Oil System\Lube Oil Average Header Pressure	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Lube Oil System\Lube Oil Differential Pressure Filter	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Lube Oil System\Lube Oil Header Pressure 1	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Lube Oil System\Lube Oil Header Pressure 2	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Lube Oil System\Lube Oil Header Pressure 3	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Lube Oil System\Lube Oil Header Temperature	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Lube Oil System\Lube Oil Pump Delivery Pressure	Parameter	Attribute
MALAYSIA\BORF\GTG\GT-2420A\Lube Oil System\Lube Oil Tank Level	Parameter	Attribute
"""

def deduce_type_and_unit(name: str):
    name_lower = name.lower()
    if "temperature" in name_lower or "temp" in name_lower:
        return "Temperature", "degC", (40.0, 110.0)
    elif "exhaust temperature" in name_lower:
        return "Exhaust Temperature", "degC", (350.0, 580.0)
    elif "vibration" in name_lower or "axial" in name_lower:
        return "Vibration", "mm/s", (0.5, 12.0)
    elif "differential pressure" in name_lower or "dp" in name_lower:
        return "Differential Pressure", "mbar", (10.0, 150.0)
    elif "pressure" in name_lower:
        return "Pressure", "barg", (1.0, 35.0)
    elif "flow" in name_lower:
        return "Flow", "kg/h", (5000.0, 45000.0)
    elif "speed" in name_lower:
        return "Speed", "RPM", (3000.0, 9500.0)
    elif "level" in name_lower:
        return "Level", "%", (40.0, 85.0)
    elif "flame" in name_lower:
        return "Flame Detector", "Intensity", (0.0, 100.0)
    elif "pos" in name_lower or "asv" in name_lower or "igv" in name_lower:
        return "Position", "%", (0.0, 100.0)
    elif "ratio" in name_lower:
        return "Ratio", "ratio", (1.2, 4.5)
    return "Process Parameter", "units", (10.0, 100.0)

sensors = []
idx = 1
for line in RAW_TABLE.strip().split("\n"):
    parts = line.strip().split("\t")
    if not parts or not parts[0]:
        continue
    parent = parts[0].strip()
    attr_name = parts[1].strip() if len(parts) > 1 else "Parameter"
    obj_type = parts[2].strip() if len(parts) > 2 else "Attribute"
    
    # Extract subsystem and tag name
    # Path pattern: MALAYSIA\BORF\GTG\GT-2420A\<Subsystem>\<Tag>
    tokens = parent.split("\\")
    if len(tokens) >= 5:
        subsystem = tokens[4]
        tag_name = "\\".join(tokens[5:]) if len(tokens) > 5 else tokens[4]
    else:
        subsystem = "General"
        tag_name = tokens[-1]
    
    param_category, unit, (sim_min, sim_max) = deduce_type_and_unit(tag_name)
    
    sensors.append({
        "id": idx,
        "selected": True,
        "parent": parent,
        "attribute_name": attr_name,
        "object_type": obj_type,
        "full_af_path": parent,  # Matches: MALAYSIA\BORF\GTG\GT-2420A\Lube Oil System\Lube Oil Tank Level
        "subsystem": subsystem,
        "tag_name": tag_name,
        "category": param_category,
        "unit": unit,
        "sim_range": [sim_min, sim_max],
        "web_id": None
    })
    idx += 1

output_path = CONFIG_DIR / "sensors.json"
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(sensors, f, indent=4)

print(f"Successfully generated {output_path} with {len(sensors)} sensor attributes.")
