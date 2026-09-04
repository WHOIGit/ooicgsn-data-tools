"""
SeaBird CTD XMLCON Parser - Enhanced Version with Comparison Tools

This module provides tools to parse XMLCON files and compare them against
calibration documentation.
"""

import xml.etree.ElementTree as ET
import pandas as pd
from typing import Dict, List, Any, Optional
import re
from pathlib import Path


class XMLCONParser:
    """Parser for SeaBird CTD XMLCON files."""
    
    def __init__(self, filepath: str):
        """
        Initialize the parser with an XMLCON file.
        
        Parameters:
        -----------
        filepath : str
            Path to the XMLCON file
        """
        self.filepath = filepath
        self.df = None
        self.tree = None
        self.root = None
        self._parse_file()
    
    def _parse_file(self):
        """Parse the XMLCON file."""
        self.tree = ET.parse(self.filepath)
        self.root = self.tree.getroot()
        self.df = self._create_dataframe()
    
    def _create_dataframe(self) -> pd.DataFrame:
        """Create DataFrame from parsed XML."""
        sensor_array = self.root.find('.//SensorArray')
        sensors_data = []
        
        for sensor in sensor_array.findall('Sensor'):
            sensor_index = sensor.get('index')
            sensor_id = sensor.get('SensorID')
            
            sensor_element = list(sensor)[0]
            sensor_type = sensor_element.tag
            
            sensor_info = {
                'sensor_index': int(sensor_index),
                'sensor_id': sensor_id,
                'sensor_type': sensor_type,
            }
            
            params = self._extract_all_parameters(sensor_element)
            sensor_info.update(params)
            
            sensors_data.append(sensor_info)
        
        df = pd.DataFrame(sensors_data)
        
        # Reorder columns
        priority_cols = ['sensor_index', 'sensor_type', 'sensor_id', 
                         'serial_number', 'calibration_date']
        other_cols = [col for col in df.columns if col not in priority_cols]
        df = df[priority_cols + other_cols]
        
        return df
    
    def _extract_all_parameters(self, element: ET.Element, prefix: str = '') -> Dict[str, Any]:
        """Recursively extract all parameters from an XML element."""
        params = {}
        
        for child in element:
            tag = child.tag
            
            if tag in ['Coefficients', 'CalibrationCoefficients']:
                equation = child.get('equation', '')
                eq_prefix = f'eq{equation}_' if equation else ''
                nested_params = self._extract_all_parameters(child, prefix=eq_prefix)
                params.update(nested_params)
            else:
                text = child.text.strip() if child.text else ''
                param_name = self._camel_to_snake(tag)
                full_param_name = f'{prefix}{param_name}'
                value = self._convert_value(text)
                params[full_param_name] = value
        
        return params
    
    @staticmethod
    def _camel_to_snake(name: str) -> str:
        """Convert CamelCase to snake_case."""
        s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
        s2 = re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1)
        return s2.lower()
    
    @staticmethod
    def _convert_value(text: str) -> Any:
        """Convert string value to appropriate Python type."""
        if not text:
            return None
        
        try:
            return int(text)
        except ValueError:
            pass
        
        try:
            return float(text)
        except ValueError:
            pass
        
        return text
    
    def get_summary(self) -> pd.DataFrame:
        """
        Get a summary DataFrame with key sensor information.
        
        Returns:
        --------
        pd.DataFrame
            Summary with sensor_index, sensor_type, serial_number, calibration_date
        """
        cols = ['sensor_index', 'sensor_type', 'serial_number', 'calibration_date']
        return self.df[cols].copy()
    
    def get_sensor(self, sensor_index: int) -> pd.Series:
        """
        Get all information for a specific sensor.
        
        Parameters:
        -----------
        sensor_index : int
            Index of the sensor
            
        Returns:
        --------
        pd.Series
            All parameters for the sensor
        """
        return self.df[self.df['sensor_index'] == sensor_index].iloc[0]
    
    def get_sensors_by_type(self, sensor_type: str) -> pd.DataFrame:
        """
        Get all sensors of a specific type.
        
        Parameters:
        -----------
        sensor_type : str
            Type of sensor (e.g., 'TemperatureSensor', 'ConductivitySensor')
            
        Returns:
        --------
        pd.DataFrame
            All sensors of the specified type
        """
        return self.df[self.df['sensor_type'] == sensor_type].copy()
    
    def get_calibration_coefficients(self, sensor_index: int) -> Dict[str, Any]:
        """
        Extract calibration coefficients for a specific sensor.
        
        Parameters:
        -----------
        sensor_index : int
            Index of the sensor
            
        Returns:
        --------
        dict
            Dictionary of calibration coefficients
        """
        sensor = self.get_sensor(sensor_index)
        
        exclude_cols = ['sensor_index', 'sensor_type', 'sensor_id', 
                        'serial_number', 'calibration_date']
        
        coeffs = {}
        for col in self.df.columns:
            if col not in exclude_cols and pd.notna(sensor[col]):
                coeffs[col] = sensor[col]
        
        return coeffs
    
    def list_sensors(self) -> None:
        """Print a formatted list of all sensors."""
        print(f"Sensors in {Path(self.filepath).name}:")
        print("=" * 80)
        for _, row in self.df.iterrows():
            sn = str(row['serial_number']) if pd.notna(row['serial_number']) else 'N/A'
            cal_date = str(row['calibration_date']) if pd.notna(row['calibration_date']) else 'N/A'
            print(f"[{row['sensor_index']:2d}] {row['sensor_type']:35s} SN: {sn:15s} Cal: {cal_date}")
    
    def export_to_csv(self, output_path: str) -> None:
        """
        Export the parsed data to CSV.
        
        Parameters:
        -----------
        output_path : str
            Path for the output CSV file
        """
        self.df.to_csv(output_path, index=False)
        print(f"Exported to {output_path}")
    
    def export_summary_to_csv(self, output_path: str) -> None:
        """
        Export just the summary to CSV.
        
        Parameters:
        -----------
        output_path : str
            Path for the output CSV file
        """
        self.get_summary().to_csv(output_path, index=False)
        print(f"Exported summary to {output_path}")
    
    def compare_sensor(self, sensor_index: int, expected_values: Dict[str, Any]) -> Dict[str, Any]:
        """
        Compare a sensor's values against expected values.
        
        Parameters:
        -----------
        sensor_index : int
            Index of the sensor to compare
        expected_values : dict
            Dictionary of expected parameter values
            
        Returns:
        --------
        dict
            Comparison results with keys:
            - 'matches': dict of matching values
            - 'mismatches': dict of mismatching values
            - 'missing_in_xmlcon': list of parameters in expected but not in XMLCON
            - 'missing_in_expected': list of parameters in XMLCON but not in expected
        """
        sensor = self.get_sensor(sensor_index)
        
        matches = {}
        mismatches = {}
        
        # Check expected values
        for key, expected_val in expected_values.items():
            if key in sensor.index:
                actual_val = sensor[key]
                if pd.isna(actual_val) and pd.isna(expected_val):
                    matches[key] = {'actual': actual_val, 'expected': expected_val}
                elif self._values_match(actual_val, expected_val):
                    matches[key] = {'actual': actual_val, 'expected': expected_val}
                else:
                    mismatches[key] = {'actual': actual_val, 'expected': expected_val}
        
        # Find missing parameters
        missing_in_xmlcon = [k for k in expected_values.keys() if k not in sensor.index]
        
        # Find extra parameters (in XMLCON but not in expected)
        exclude_cols = ['sensor_index', 'sensor_type', 'sensor_id']
        actual_params = [col for col in sensor.index if col not in exclude_cols and pd.notna(sensor[col])]
        missing_in_expected = [k for k in actual_params if k not in expected_values.keys()]
        
        return {
            'matches': matches,
            'mismatches': mismatches,
            'missing_in_xmlcon': missing_in_xmlcon,
            'missing_in_expected': missing_in_expected
        }
    
    @staticmethod
    def _values_match(val1: Any, val2: Any, tolerance: float = 1e-10) -> bool:
        """
        Check if two values match (with tolerance for floats).
        
        Parameters:
        -----------
        val1, val2 : Any
            Values to compare
        tolerance : float
            Tolerance for float comparison
            
        Returns:
        --------
        bool
            True if values match
        """
        # Handle None/NaN
        if pd.isna(val1) and pd.isna(val2):
            return True
        if pd.isna(val1) or pd.isna(val2):
            return False
        
        # Handle numeric values
        if isinstance(val1, (int, float)) and isinstance(val2, (int, float)):
            return abs(float(val1) - float(val2)) < tolerance
        
        # Handle strings
        return str(val1) == str(val2)
    
    def print_comparison(self, sensor_index: int, expected_values: Dict[str, Any]) -> None:
        """
        Print a formatted comparison report.
        
        Parameters:
        -----------
        sensor_index : int
            Index of the sensor to compare
        expected_values : dict
            Dictionary of expected parameter values
        """
        sensor = self.get_sensor(sensor_index)
        comparison = self.compare_sensor(sensor_index, expected_values)
        
        print(f"\nComparison for Sensor {sensor_index}: {sensor['sensor_type']}")
        print(f"Serial Number: {sensor['serial_number']}")
        print(f"Calibration Date: {sensor['calibration_date']}")
        print("=" * 80)
        
        if comparison['matches']:
            print(f"\n✓ MATCHES ({len(comparison['matches'])} parameters):")
            for key, vals in sorted(comparison['matches'].items()):
                print(f"  {key}: {vals['actual']}")
        
        if comparison['mismatches']:
            print(f"\n✗ MISMATCHES ({len(comparison['mismatches'])} parameters):")
            for key, vals in sorted(comparison['mismatches'].items()):
                print(f"  {key}:")
                print(f"    Expected: {vals['expected']}")
                print(f"    Actual:   {vals['actual']}")
        
        if comparison['missing_in_xmlcon']:
            print(f"\n⚠ MISSING IN XMLCON ({len(comparison['missing_in_xmlcon'])} parameters):")
            for key in sorted(comparison['missing_in_xmlcon']):
                print(f"  {key}: {expected_values[key]}")
        
        if comparison['missing_in_expected']:
            print(f"\n⚠ EXTRA IN XMLCON ({len(comparison['missing_in_expected'])} parameters):")
            for key in sorted(comparison['missing_in_expected']):
                print(f"  {key}: {sensor[key]}")


# Example usage
if __name__ == '__main__':
    # Parse the XMLCON file
    parser = XMLCONParser('/mnt/user-data/uploads/AR98A_013.XMLCON')
    
    # Show sensor list
    parser.list_sensors()
    print("\n")
    
    # Get summary
    print("Summary DataFrame:")
    print(parser.get_summary().to_string())
    print("\n")
    
    # Example: Compare Temperature Sensor at index 0
    print("=" * 80)
    print("Example Comparison:")
    print("=" * 80)
    
    expected_temp_coeffs = {
        'serial_number': '4039',
        'calibration_date': '05-Nov-24',
        'g': 4.41256032e-003,
        'h': 6.49196754e-004,
        'i': 2.36876027e-005,
        'j': 2.13829165e-006,
        'f0': 1000.000,
        'slope': 1.00000000,
        'offset': 0.0000,
    }
    
    parser.print_comparison(0, expected_temp_coeffs)
