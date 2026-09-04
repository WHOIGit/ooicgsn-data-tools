#!/usr/bin/env python
"""
Smoke tests for cruise_tools.ctd parsers.

These tests require no calibration PDFs — they only verify that the
module imports cleanly and the XMLCONParser handles a minimal XML string.
"""
import textwrap
import tempfile
import os
import pytest


def _minimal_xmlcon() -> str:
    """Return a minimal valid XMLCON XML string for testing."""
    return textwrap.dedent("""\
        <?xml version="1.0" encoding="UTF-8"?>
        <SBE_InstrumentConfiguration SB_ConfigCTD_FileVersion="7.26.4">
          <Instrument Type="11">
            <SensorArray Size="2">
              <Sensor index="0" SensorID="58">
                <TemperatureSensor SensorID="58">
                  <SerialNumber>4039</SerialNumber>
                  <CalibrationDate>13-Nov-23</CalibrationDate>
                  <A0>1.25e-003</A0><A1>2.75e-004</A1><A2>-2.5e-006</A2>
                  <A3>2.1e-007</A3>
                  <Slope>1.0</Slope><Offset>0.0</Offset>
                  <G>4.41256032e-003</G><H>6.32113795e-004</H>
                  <I>1.8e-005</I><J>1.5e-006</J>
                  <F0>1000</F0><Wbotc>3.2e-006</Wbotc>
                  <UseG_J>1</UseG_J>
                </TemperatureSensor>
              </Sensor>
              <Sensor index="1" SensorID="3">
                <PressureSensor SensorID="3">
                  <SerialNumber>0</SerialNumber>
                  <CalibrationDate></CalibrationDate>
                  <C1>0</C1><C2>0</C2><C3>0</C3>
                  <D1>0</D1><D2>0</D2>
                  <T1>0</T1><T2>0</T2><T3>0</T3><T4>0</T4><T5>0</T5>
                  <Slope>1.0</Slope><Offset>0.0</Offset>
                  <AD590M>0</AD590M><AD590B>0</AD590B>
                </PressureSensor>
              </Sensor>
            </SensorArray>
          </Instrument>
        </SBE_InstrumentConfiguration>
    """)


def test_xmlcon_parser_import():
    from cruise_tools.ctd import XMLCONParser  # noqa: F401


def test_xmlcon_parser_minimal():
    from cruise_tools.ctd import XMLCONParser

    xml = _minimal_xmlcon()
    with tempfile.NamedTemporaryFile(mode="w", suffix=".XMLCON",
                                     delete=False) as f:
        f.write(xml)
        path = f.name
    try:
        parser = XMLCONParser(path)
        assert len(parser.df) >= 1
        temp_rows = parser.df[parser.df["sensor_type"] == "TemperatureSensor"]
        assert len(temp_rows) == 1
        assert str(temp_rows.iloc[0]["serial_number"]) == "4039"
    finally:
        os.unlink(path)


def test_cal_pdf_parser_import():
    from cruise_tools.ctd import (  # noqa: F401
        parse_cal_pdf, parse_flntu_pdf, parse_cdom_pdf,
        compare_cal_to_xmlcon, print_comparison,
    )


def test_compare_cal_structure():
    """compare_cal_to_xmlcon returns the expected dict keys even with dummy data."""
    from cruise_tools.ctd import compare_cal_to_xmlcon
    import pandas as pd

    cal = {
        "sensor_type": "TemperatureSensor",
        "serial_number": "4039",
        "calibration_date": "2023-11-13",
        "g": 4.41256032e-3,
        "h": 6.32113795e-4,
    }
    xmlcon_row = pd.Series({
        "sensor_type": "TemperatureSensor",
        "serial_number": "4039",
        "calibration_date": "13-Nov-23",
        "g": 4.41256032e-3,
        "h": 6.32113795e-4,
    })
    result = compare_cal_to_xmlcon(cal, xmlcon_row)
    assert "serial_match" in result
    assert "coeff_matches" in result
    assert "coeff_mismatches" in result
    assert result["serial_match"] is True
    assert "g" in result["coeff_matches"]
