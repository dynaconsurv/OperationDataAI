"""Populate config/sensors.json from the user's updated AF attributes table,
binding each sensor to its discovered live PI AF WebID.
"""

import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
CONFIG_DIR = BASE_DIR / "config"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)

RAW_TABLE = r"""
MALAYSIA\BORF\GTG\GT-2420A\Air Filter System\Ambient Inlet Pressure	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Air Filter System\High Differential Pressure High Eff. Filter ATM	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Air Filter System\High Differential Pressure High Efficiency	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Air Filter System\High Differential Pressure Prefilter	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Compressor\Compressor Journal Bearing Temperature 1	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Compressor\Compressor Journal Bearing Temperature 2	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Compressor\Compressor Journal Bearing Temperature 3	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Compressor\Compressor Journal Bearing Temperature 4	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Compressor\Compressor Shaft Axial Display A	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Compressor\Compressor Shaft Axial Display B	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Compressor\Compressor Shaft X Radial Vibration 1	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Compressor\Compressor Shaft X Radial Vibration 2	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Compressor\Compressor Shaft Y Radial Vibration 1	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Compressor\Compressor Shaft Y Radial Vibration 2	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Compressor\Compressor Thrust Bearing Active Side Temperature1	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Compressor\Compressor Thrust Bearing Non Active Side Temperature 1	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Compressor Process\1st Stage Anti Surge Valve	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Compressor Process\1st Stage Compressor Inlet Flow	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Compressor Process\1st Stage Compressor Inlet Pressure	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Compressor Process\1st Stage Compressor Inlet Temperature	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Compressor Process\1st Stage Compressor Outlet Pressure	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Compressor Process\1st Stage Compressor Outlet Temperature	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Compressor Process\1st Stage Compressor Ratio	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Compressor Process\2nd Stage Anti Surge Valve	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Compressor Process\2nd Stage Compressor Inlet Flow	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Compressor Process\2nd Stage Compressor Inlet Pressure	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Compressor Process\2nd Stage Compressor Inlet Temperature	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Compressor Process\2nd Stage Compressor Outlet Pressure	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Compressor Process\2nd Stage Compressor Outlet Temperature	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Compressor Process\2nd Stage Compressor Ratio	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Compressor Process\Anti Surge Valve Position Transmitter 1	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Compressor Process\Anti Surge Valve Position Transmitter 2	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Compressor Process\Compressor Suction Pressure	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Dry Gas Seal System\Buffer Seal Gas Inlet Valve Positioner I/P Positioner	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Dry Gas Seal System\CC Sealing Chamber Vent Discharge Side Pressure	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Dry Gas Seal System\CC Sealing Chamber Vent Suction Side Pressure	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Dry Gas Seal System\Compressor Discharge End Primary Vent Flow	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Dry Gas Seal System\Compressor Primary Vent Pressure 1	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Dry Gas Seal System\Compressor Primary Vent Pressure 2	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Dry Gas Seal System\Compressor Primary Vent Pressure 3	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Dry Gas Seal System\Compressor Primary Vent Pressure 4	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Dry Gas Seal System\Compressor Primary Vent Pressure 5	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Dry Gas Seal System\Compressor Primary Vent Pressure 6	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Dry Gas Seal System\Compressor Suction End Primary Vent Flow	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Dry Gas Seal System\N2 Filter Diffirential Pressure	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Dry Gas Seal System\Seal Gas Amplifier Differential Pressure	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Dry Gas Seal System\Seal Gas Balancing Line Pressure 1	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Dry Gas Seal System\Seal Gas Downstream Electric Heater Temperature 1	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Dry Gas Seal System\Seal Gas Downstream Electric Heater Temperature 2	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Dry Gas Seal System\Seal Gas Downstream Electric Heater Temperature 3	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Dry Gas Seal System\Seal Gas Filters Differential Pressure	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Dry Gas Seal System\Seal Gas Inlet Balancing Line Pressure	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Dry Gas Seal System\Tertiary Seal Gas Pressure	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Dry Gas Seal System\Tertiary Seal Gas Pressure Pressure	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Dry Gas Seal System\Tertiary Seal Gas Pressure Pressure  1	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Dry Gas Seal System\Tertiary Seal Gas Pressure Pressure 2	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Enclosure System\Acc. Compart. Vent. Outlet Gas Detector	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Enclosure System\Coupling Compartment Internal Temperature	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Enclosure System\G.T. Compart. Vent. Outlet Gas Detector	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Enclosure System\Gas Detector Inlet Air Filter Ir Gas Detector	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Enclosure System\Turbine Compartment Internal Temperature 1	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Enclosure System\Turbine Compartment Internal Temperature 2	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Enclosure System\Turbine Compartment Internal Temperature 3	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Enclosure System\Turbine Compartment Ventilation Pressure 1	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Enclosure System\Turbine Compartment Ventilation Pressure 2	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Enclosure System\Turbine Compartment Ventilation Pressure 3	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Fuel Gas System\Fuel Gas Control Valve Position	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Fuel Gas System\Fuel Gas Inlet Pressure Measurement Pressure	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Fuel Gas System\Fuel Gas Inlet Temperature Rtd	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Fuel Gas System\Fuel Gas Pressure Upstream Valve Pressure	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Fuel Gas System\Fuel Gas Stop/Speed Ratio Valve Position	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Fuel Gas System\Interstage Fuel Gas Pressure Pressure 1	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Fuel Gas System\Interstage Fuel Gas Pressure Pressure 2	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Fuel Gas System\Interstage Fuel Gas Pressure Pressure 3	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Average Axial Discharge Pressure	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Average Exhaust Temperature	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Axial Compressor Discharge Pressure	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Axial Compressor Discharge Pressure 1	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Axial Compressor Discharge Pressure 2	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Axial Compressor Discharge Temperature 1	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Axial Compressor Discharge Temperature 2	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Axial Compressor Inlet Temperature 1	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Axial Compressor Inlet Temperature 2	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Exhaust Duct Back Pressure	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Exhaust Temperature 1	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Exhaust Temperature 10	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Exhaust Temperature 11	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Exhaust Temperature 12	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Exhaust Temperature 13	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Exhaust Temperature 2	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Exhaust Temperature 3	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Exhaust Temperature 4	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Exhaust Temperature 5	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Exhaust Temperature 6	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Exhaust Temperature 7	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Exhaust Temperature 8	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Exhaust Temperature 9	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Flame Detector Combustion Chamber 10	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Flame Detector Combustion Chamber 11	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Flame Detector Combustion Chamber 2	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Flame Detector Combustion Chamber 3	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\HP Rotor Axial Displacement Displacement Probe Proximitor 1	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\HP Rotor Axial Displacement Displacement Probe Proximitor 2	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\HP Shaft Magnetic Speed Pick Up	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\HP Shaft Speed Control	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\HP Shaft Vibration Seismic Probe	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Journal Bearing 1 Drain Oil Temperature	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Journal Bearing 2 Drain Oil Temperature	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Journal Bearing 3 Drain Oil Temperature	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Journal Bearing 4 Metal Temperature	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Journal Thrust Bearing 4 Drain Oil Temperature	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\LP Rotor Axial Displacement Displacement Probe Proximitor 1	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\LP Rotor Axial Displacement Displacement Probe Proximitor 2	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\LP Shaft Magnetic Speed Pick Up	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\LP Shaft Speed Control	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\LP Shaft Vibration Seismic Probe	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Spread Exhaust Temperature	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Thrust Bearing 1 Drain Oil Temperature	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Thrust Bearing 4 Active Temperature	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Thrust Bearing 4 Inactive Temperature	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Turbine 2nd Stage Nozzles Position	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Turbine Bearing 1 Radial Vibrations Vibration Probe Proximitor	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Turbine Bearing Radial Vibrations Vibration Probe Proximitor	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Turbine IGV Position	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Wheel Space Temperature 1st Stage Aft Inner #1	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Wheel Space Temperature 1St Stage Fwd Inner #1	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Wheel Space Temperature 2nd Stage Aft Inner #1	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Gas Turbine Engine\Wheel Space Temperature 2nd Stage Fwd Inner #1	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Gearbox\Gear-Box  Wheel Casing Accelerator Sensor	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Gearbox\Gear-Box  Wheel DE Journal Bearing Temperature 2	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Gearbox\Gear-Box  Wheel NDE Journal Bearing Temperature 1	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Gearbox\Gear-Box  Wheel NDE Journal Bearing Temperature 2	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Gearbox\Gear-Box  Wheel Thrust Bearing Active Side Temperature 1	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Gearbox\Gear-Box  Wheel Thrust Bearing Active Side Temperature 2	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Gearbox\Gear-Box  Wheel Thrust Bearing Non Active Temperature 1	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Gearbox\Gear-Box Pinion De Bearing X Radial Vibration	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Gearbox\Gear-Box Pinion De Bearing Y Radial Vibration	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Gearbox\Gear-Box Pinion DE Journal Bearing 2	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Gearbox\Gear-Box Pinion NDE Bearing X Radial Vibration	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Gearbox\Gear-Box Pinion NDE Bearing Y Radial Vibration	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Gearbox\Gear-Box Pinion NDE Journal Bearing Temperature 2	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Gearbox\Gear-Box Wheel Axial Bearing Display 1	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Gearbox\Gear-Box Wheel Axial Bearing Display 2	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Gearbox\Gear-Box Wheel DE Bearing X Radial Vibration	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Gearbox\Gear-Box Wheel DE Bearing Y Radial Vibration	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Gearbox\Gearbox Wheel DE Journal Bearing Temperature 1	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Gearbox\Gear-Box Wheel NDE Bearing X Radial Vib.	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Gearbox\Gear-Box Wheel NDE Bearing Y Radial Vibration	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Gearbox\Gearbox Wheel Thrust Bearing Non Active Temperature 2	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Hydraulic System\Control Oil Header Pressure	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Hydraulic System\Control Oil Header Pressure 1	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Hydraulic System\Control Oil Header Pressure 2	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Hydraulic System\Hydraulic Oil Filters High Differential Pressure	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Hydraulic System\Hydraulic Oil Header Low Pressure	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Lube Oil System\Lube Oil Average Header Pressure	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Lube Oil System\Lube Oil Differential Pressure Filter	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Lube Oil System\Lube Oil Header Pressure 1	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Lube Oil System\Lube Oil Header Pressure 2	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Lube Oil System\Lube Oil Header Pressure 3	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Lube Oil System\Lube Oil Header Temperature	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Lube Oil System\Lube Oil Pumps Low Delivery Pressure	Parameter
MALAYSIA\BORF\GTG\GT-2420A\Lube Oil System\Lube Oil Tank Level	Parameter
"""

# Map user variants to exact PI AF element names
AF_ALIASES = {
    ("Air Filter System", "High Differential Pressure High Eff. Filter ATM"): "High Differential Pressure High Efficiency Filter ATM",
    ("Compressor", "Compressor Shaft Axial Display A"): "Compressor Shaft Axial Displacement A",
    ("Compressor", "Compressor Shaft Axial Display B"): "Compressor Shaft Axial Displacement B",
    ("Compressor", "Compressor Shaft X Radial Vibration 1"): "Compressor Shaft DE X Radial Vibration",
    ("Compressor", "Compressor Shaft X Radial Vibration 2"): "Compressor Shaft NDE X Radial Vibration",
    ("Compressor", "Compressor Shaft Y Radial Vibration 1"): "Compressor Shaft DE Y Radial Vibration",
    ("Compressor", "Compressor Shaft Y Radial Vibration 2"): "Compressor Shaft NDE Y Radial Vibration",
    ("Compressor Process", "Anti Surge Valve Position Transmitter 1"): "1st Stage Anti Surge Valve Position",
    ("Compressor Process", "Anti Surge Valve Position Transmitter 2"): "2nd Stage Anti Surge Valve Position",
    ("Dry Gas Seal System", "Compressor Primary Vent Pressure 1"): "Compressor Suction End Primary Vent Pressure 1",
    ("Dry Gas Seal System", "Compressor Primary Vent Pressure 2"): "Compressor Suction End Primary Vent Pressure 2",
    ("Dry Gas Seal System", "Compressor Primary Vent Pressure 3"): "Compressor Suction End Primary Vent Pressure 3",
    ("Dry Gas Seal System", "Compressor Primary Vent Pressure 4"): "Compressor Discharge End Primary Vent Pressure 1",
    ("Dry Gas Seal System", "Compressor Primary Vent Pressure 5"): "Compressor Discharge End Primary Vent Pressure 2",
    ("Dry Gas Seal System", "Compressor Primary Vent Pressure 6"): "Compressor Discharge End Primary Vent Pressure 3",
    ("Dry Gas Seal System", "Tertiary Seal Gas Pressure Pressure"): "Tertiary Seal Gas Pressure Pressure 3",
    ("Gas Turbine Engine", "Axial Compressor Discharge Pressure"): "Axial Compressor Discharge Pressure 3",
    ("Gearbox", "Gear-Box Wheel Axial Bearing Display 1"): "Gear-Box Wheel Axial Bearing Displacement 1",
    ("Gearbox", "Gear-Box Wheel Axial Bearing Display 2"): "Gear-Box Wheel Axial Bearing Displacement 2",
    ("Gearbox", "Gear-Box Wheel NDE Bearing X Radial Vib."): "Gear-Box Wheel NDE Bearing X Radial Vibration",
    ("Hydraulic System", "Control Oil Header Pressure"): "Control Oil Header Pressure 3",
}


def deduce_type_and_unit(name: str):
    name_lower = name.lower()
    if "exhaust temperature" in name_lower:
        return "Exhaust Temperature", "degC", (350.0, 580.0)
    elif "temperature" in name_lower or "temp" in name_lower or "rtd" in name_lower:
        return "Temperature", "degC", (40.0, 110.0)
    elif "vibration" in name_lower or "axial" in name_lower or "accelerator" in name_lower or "vib." in name_lower:
        return "Vibration", "mm/s", (0.5, 12.0)
    elif "differential pressure" in name_lower or "diffirential pressure" in name_lower or "dp" in name_lower:
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
    elif "gas detector" in name_lower:
        return "Gas Detector", "% LEL", (0.0, 25.0)
    elif "position" in name_lower or "valve" in name_lower or "asv" in name_lower or "igv" in name_lower or "nozzles" in name_lower:
        return "Position", "%", (0.0, 100.0)
    elif "ratio" in name_lower:
        return "Ratio", "ratio", (1.2, 4.5)
    return "Process Parameter", "units", (10.0, 100.0)


def build_catalog():
    # Load discovered AF elements for WebID binding
    af_file = BASE_DIR / "data" / "af_discovered.json"
    af_map = {}
    if af_file.exists():
        with open(af_file, "r", encoding="utf-8") as f:
            for item in json.load(f):
                af_map[(item["subsystem"], item["element_name"])] = item

    sensors = []
    idx = 1

    for line in RAW_TABLE.strip().splitlines():
        parts = line.strip().split("\t")
        if not parts or not parts[0]:
            continue
        parent = parts[0].strip()
        attr_name = parts[1].strip() if len(parts) > 1 else "Parameter"
        obj_type = "Attribute"

        tokens = parent.split("\\")
        subsystem = tokens[4] if len(tokens) >= 5 else "General"
        tag_name = tokens[-1]

        # Resolve target AF element name
        target_af_elem = AF_ALIASES.get((subsystem, tag_name), tag_name)
        af_item = af_map.get((subsystem, target_af_elem), {})
        web_id = af_item.get("web_id")

        param_category, unit, (sim_min, sim_max) = deduce_type_and_unit(tag_name)

        sensor_obj = {
            "id": idx,
            "selected": True,
            "parent": parent,
            "attribute_name": attr_name,
            "object_type": obj_type,
            "full_af_path": parent,
            "subsystem": subsystem,
            "tag_name": tag_name,
            "category": param_category,
            "unit": unit,
            "sim_range": [sim_min, sim_max],
            "web_id": web_id,
        }
        sensors.append(sensor_obj)
        idx += 1

    output_path = CONFIG_DIR / "sensors.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(sensors, f, indent=2)

    print(f"Successfully generated {len(sensors)} sensors in {output_path}!")
    with_webid = sum(1 for s in sensors if s.get("web_id"))
    print(f"Sensors with mapped WebID: {with_webid} / {len(sensors)}")


if __name__ == "__main__":
    build_catalog()
