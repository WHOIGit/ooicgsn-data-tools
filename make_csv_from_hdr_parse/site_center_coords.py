import pandas as pd
from geopy.distance import geodesic


def check_within_radius(lat, lon, centers_df, radius):
    for _, center in centers_df.iterrows():
        center_lat = center['lat']
        center_lon = center['lon']
        center_name = center.get('site', 'Unnamed Site')

        distance = geodesic((lat, lon), (center_lat, center_lon)).kilometers
        if distance <= radius:
            return True, center_name  # Return True and the site name if within radius
    return False, None  # Return False if not within any radius


def process_csv(points_csv, sites_csv, output_csv, radius):
    # Read the points and site centers CSV files
    points_df = pd.read_csv(points_csv)
    centers_df = pd.read_csv(sites_csv)

    # Prepare a list to store results
    results = []
    site_names = []

    for _, point in points_df.iterrows():
        lat = point['latitude']
        lon = point['longitude']

        within_radius, site_name = check_within_radius(lat, lon, centers_df, radius)
        results.append(within_radius)
        site_names.append(site_name)

    # Add results to the points DataFrame
    points_df['within_radius'] = results
    points_df['site_name'] = site_names

    # Write the updated DataFrame to a new CSV file
    points_df.to_csv(output_csv, index=False)
    print(f"Processed file saved as {output_csv}")


# Example usage
points_csv = '/Users/sawyer/Desktop/AR82-Pioneer20/ifcb-test-dir/ifcb-parsing-processing/make_csv_from_hdr_parse/2024-08-21_underway_latlon_merged_output.csv'
sites_csv = '/Volumes/My Passport/IFCB_PLIMS/PioneerMAB_IFCB_Dashboard_Metadata/site_center_coords.csv'
output_csv = 'output_2024-08-21.csv'  # Path to your output CSV file
radius = 2  # Radius in kilometers

process_csv(points_csv, sites_csv, output_csv, radius)

