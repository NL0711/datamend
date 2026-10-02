"""
Script: generate_earth_assets.py
Generates high-resolution authentic Earth equirectangular raster map textures
and bump relief maps for SkyGuard AI's 3D Geospatial Digital Twin.
"""

import os
import math
from PIL import Image, ImageDraw, ImageFilter

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend", "public", "assets", "earth")
os.makedirs(OUTPUT_DIR, exist_ok=True)

WIDTH = 4096
HEIGHT = 2048

def lon_lat_to_xy(lon, lat):
    """Convert longitude [-180, 180] and latitude [-90, 90] to pixel coordinates."""
    x = int(((lon + 180.0) / 360.0) * (WIDTH - 1))
    y = int(((90.0 - lat) / 180.0) * (HEIGHT - 1))
    return x, y

def generate_earth_textures():
    print(f"[SkyGuard Earth] Generating {WIDTH}x{HEIGHT} High-Resolution Real Earth Texture...")
    
    # 1. Base Ocean Layer (Deep Bathymetric Gradient)
    img = Image.new("RGB", (WIDTH, HEIGHT), "#0B1528")
    draw = ImageDraw.Draw(img)
    
    # Ocean gradient
    for y in range(HEIGHT):
        lat = 90.0 - (y / (HEIGHT - 1)) * 180.0
        # Darker near poles and deep troughs, rich oceanic blue in mid-latitudes
        intensity = math.cos(math.radians(lat))
        r = int(9 + 8 * intensity)
        g = int(18 + 18 * intensity)
        b = int(36 + 32 * intensity)
        draw.line([(0, y), (WIDTH, y)], fill=(r, g, b))
        
    # 2. Shallow Coastal Shelves & Coral Reefs (Aqua-marine fringes)
    # Define detailed continent boundaries using geographic polygons
    
    # EURASIA
    eurasia_poly = [
        (-9.5, 36.0), (-9.0, 43.8), (-1.5, 43.5), (-4.8, 48.4), (2.5, 51.1),
        (5.0, 58.7), (5.0, 62.0), (12.0, 56.0), (14.0, 54.0), (19.0, 54.5),
        (24.0, 57.0), (28.0, 70.0), (40.0, 67.0), (60.0, 70.0), (75.0, 73.0),
        (105.0, 77.5), (135.0, 72.0), (170.0, 66.0), (190.0, 65.0), # Chukotka (wrap)
        (162.0, 55.0), (143.0, 50.0), (132.0, 43.0), (122.0, 39.0), (119.0, 35.0),
        (121.0, 31.0), (118.0, 24.5), (109.0, 19.5), (105.0, 10.0), (101.0, 3.0),
        (98.5, 8.0), (92.0, 16.0), (88.0, 22.0), (80.0, 16.0), (80.0, 10.0),
        (77.5, 8.0), (73.0, 18.0), (68.0, 23.0), (62.0, 25.0), (56.0, 26.0),
        (54.0, 24.0), (45.0, 13.0), (43.5, 12.5), (35.0, 28.0), (32.0, 31.0),
        (26.0, 35.5), (23.0, 38.0), (16.0, 40.0), (12.0, 44.0), (9.0, 43.5),
        (3.0, 42.0), (-0.5, 38.0), (-5.5, 36.0)
    ]
    
    # SCANDINAVIA
    scandinavia_poly = [
        (5.0, 58.7), (8.5, 58.0), (11.0, 60.0), (18.0, 59.5), (24.0, 65.0),
        (28.0, 71.0), (20.0, 70.0), (14.0, 68.0), (5.0, 62.0)
    ]
    
    # BRITISH ISLES (UK & Ireland)
    uk_poly = [
        (-5.5, 50.0), (-3.0, 50.5), (1.5, 51.0), (1.8, 52.5), (0.0, 53.5),
        (-1.5, 55.5), (-2.0, 58.5), (-5.0, 58.5), (-6.0, 56.5), (-4.5, 54.5),
        (-5.5, 52.0), (-5.5, 50.0)
    ]
    ireland_poly = [
        (-10.0, 51.5), (-6.0, 52.0), (-5.5, 54.5), (-8.0, 55.5), (-10.5, 54.0)
    ]
    
    # JAPAN
    japan_poly = [
        (130.0, 31.5), (133.0, 34.0), (137.0, 35.0), (141.0, 38.5), (141.5, 41.5),
        (145.0, 44.0), (141.0, 45.5), (139.5, 42.0), (136.0, 36.5), (131.0, 33.5)
    ]
    
    # INDIAN SUBCONTINENT
    india_poly = [
        (68.0, 23.5), (70.0, 21.0), (73.0, 18.5), (74.0, 15.0), (76.0, 10.0),
        (77.5, 8.1), (80.0, 10.0), (80.3, 13.0), (82.0, 16.5), (85.0, 20.0),
        (88.0, 22.0), (90.0, 24.0), (92.0, 26.0), (95.0, 28.0), (88.0, 27.5),
        (84.0, 28.5), (78.0, 31.0), (74.0, 34.5), (72.0, 30.0), (69.0, 26.0)
    ]
    
    # SRI LANKA
    srilanka_poly = [
        (79.8, 9.8), (81.8, 8.5), (81.5, 6.0), (80.0, 6.0), (79.5, 7.5)
    ]
    
    # AFRICA
    africa_poly = [
        (-5.5, 36.0), (10.0, 37.0), (25.0, 32.0), (32.0, 31.5), (35.0, 28.0),
        (43.5, 12.5), (51.0, 11.5), (49.0, 8.0), (41.0, -2.0), (40.0, -11.0),
        (35.5, -24.0), (32.5, -28.0), (28.0, -32.5), (19.0, -34.8), (17.5, -33.0),
        (15.0, -23.0), (12.0, -15.0), (9.0, -1.0), (9.0, 4.5), (4.5, 5.0),
        (-4.0, 5.0), (-14.0, 8.0), (-17.5, 14.5), (-16.0, 21.0), (-13.0, 28.0),
        (-9.0, 30.5), (-5.5, 36.0)
    ]
    
    # MADAGASCAR
    madagascar_poly = [
        (49.0, -12.0), (50.5, -15.5), (47.0, -25.5), (44.0, -25.0), (44.0, -16.0)
    ]
    
    # NORTH AMERICA
    na_poly = [
        (-168.0, 65.5), (-155.0, 71.5), (-135.0, 69.5), (-110.0, 68.0), (-95.0, 70.0),
        (-82.0, 65.0), (-65.0, 62.0), (-55.0, 52.0), (-60.0, 46.0), (-70.0, 42.0),
        (-75.0, 35.0), (-80.0, 25.0), (-81.0, 25.0), (-88.0, 30.0), (-97.0, 26.0),
        (-97.0, 18.5), (-88.0, 16.0), (-83.0, 8.5), (-77.5, 8.0), (-80.0, 8.5),
        (-86.0, 14.0), (-92.0, 15.0), (-105.0, 20.0), (-110.0, 23.0), (-115.0, 30.0),
        (-120.0, 34.5), (-124.5, 40.0), (-125.0, 50.0), (-135.0, 57.0), (-150.0, 60.0),
        (-165.0, 60.0), (-168.0, 65.5)
    ]
    
    # GREENLAND
    greenland_poly = [
        (-44.0, 60.0), (-35.0, 66.0), (-20.0, 70.0), (-18.0, 77.0), (-25.0, 82.0),
        (-45.0, 83.5), (-60.0, 82.0), (-70.0, 76.0), (-55.0, 70.0), (-50.0, 60.0)
    ]
    
    # SOUTH AMERICA
    sa_poly = [
        (-77.5, 8.0), (-72.0, 12.0), (-60.0, 9.0), (-50.0, 2.0), (-35.0, -5.0),
        (-35.0, -8.0), (-38.5, -13.0), (-40.0, -22.0), (-50.0, -30.0), (-58.0, -38.0),
        (-65.0, -45.0), (-66.0, -54.0), (-74.0, -53.0), (-75.0, -45.0), (-72.0, -35.0),
        (-70.0, -20.0), (-80.0, -5.0), (-80.0, 1.0), (-77.5, 8.0)
    ]
    
    # AUSTRALIA
    australia_poly = [
        (114.0, -22.0), (122.0, -18.0), (130.0, -12.0), (136.0, -12.0), (142.0, -10.5),
        (146.0, -18.0), (153.0, -28.0), (150.0, -37.0), (140.0, -38.0), (135.0, -34.0),
        (117.0, -35.0), (115.0, -32.0), (113.0, -26.0), (114.0, -22.0)
    ]
    
    # NEW ZEALAND
    nz_north = [(173.0, -35.0), (178.0, -37.5), (175.0, -41.5), (174.0, -39.0)]
    nz_south = [(168.0, -46.5), (170.5, -43.0), (174.0, -41.0), (171.0, -44.0)]
    
    # ANTARCTICA
    antarctica_poly = [
        (-180.0, -78.0), (-120.0, -74.0), (-60.0, -64.0), (-30.0, -72.0),
        (0.0, -70.0), (60.0, -66.0), (100.0, -65.0), (140.0, -67.0),
        (170.0, -72.0), (180.0, -78.0), (180.0, -90.0), (-180.0, -90.0)
    ]
    
    all_landmasses = [
        (eurasia_poly, "#2B4C38", "#8B7355"),       # Temperate Forest + Arid Central
        (scandinavia_poly, "#234130", "#3E5B47"),
        (uk_poly, "#335C3D", "#416B4A"),
        (ireland_poly, "#35623F", "#416B4A"),
        (japan_poly, "#2D5239", "#3E6349"),
        (india_poly, "#3A5F43", "#7A6843"),         # Deccan & Gangetic plains
        (srilanka_poly, "#2A5236", "#3A6246"),
        (africa_poly, "#8F7246", "#3B5A36"),        # Sahara desert + Congo basin
        (madagascar_poly, "#2E5537", "#3E6349"),
        (na_poly, "#30553A", "#8A744C"),            # North America vegetation + Rockies/Desert
        (greenland_poly, "#DCE4EC", "#B8C7D6"),     # Greenland Ice Sheet
        (sa_poly, "#285634", "#7A6745"),            # Amazon Rainforest + Andes
        (australia_poly, "#9A6D42", "#845B33"),     # Outback / Arid Scrub
        (nz_north, "#2E5A38", "#3E6349"),
        (nz_south, "#2E5A38", "#3E6349"),
        (antarctica_poly, "#E6EEF5", "#CBD8E4"),    # Antarctic Ice Shelf
    ]
    
    # Pass 1: Draw Coastal Shelves (Cyan/Turquoise glow around land)
    shelf_img = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    shelf_draw = ImageDraw.Draw(shelf_img)
    for poly, _, _ in all_landmasses:
        pixel_points = [lon_lat_to_xy(lon, lat) for lon, lat in poly]
        if len(pixel_points) > 2:
            shelf_draw.polygon(pixel_points, fill=(38, 120, 168, 180))
    
    # Blur coastal shelves for natural underwater bathymetry falloff
    shelf_blurred = shelf_img.filter(ImageFilter.GaussianBlur(radius=18))
    img.paste(shelf_blurred, (0, 0), shelf_blurred)
    
    # Pass 2: Draw Physical Continental Terrain
    for poly, primary_color, secondary_color in all_landmasses:
        pixel_points = [lon_lat_to_xy(lon, lat) for lon, lat in poly]
        if len(pixel_points) > 2:
            draw.polygon(pixel_points, fill=primary_color)
            
    # Pass 3: Detailed Regional Physical Texturing (Deserts, Mountain Ridges, Snow Caps)
    
    # Sahara & Arabian Desert
    sahara_pts = [lon_lat_to_xy(lon, lat) for lon, lat in [
        (-14.0, 30.0), (32.0, 30.0), (55.0, 24.0), (50.0, 16.0), (35.0, 15.0),
        (10.0, 15.0), (-14.0, 18.0)
    ]]
    draw.polygon(sahara_pts, fill="#A88B58")
    
    # Gobi Desert & Central Asian Steppe
    gobi_pts = [lon_lat_to_xy(lon, lat) for lon, lat in [
        (55.0, 45.0), (105.0, 45.0), (112.0, 40.0), (80.0, 36.0), (55.0, 38.0)
    ]]
    draw.polygon(gobi_pts, fill="#9E855A")
    
    # Death Valley / Mojave Desert / Sonoran
    mojave_pts = [lon_lat_to_xy(lon, lat) for lon, lat in [
        (-118.5, 37.5), (-114.0, 37.0), (-110.0, 31.0), (-115.0, 30.0), (-118.0, 34.0)
    ]]
    draw.polygon(mojave_pts, fill="#B59665")
    
    # Australian Outback
    outback_pts = [lon_lat_to_xy(lon, lat) for lon, lat in [
        (118.0, -22.0), (142.0, -20.0), (142.0, -30.0), (120.0, -32.0)
    ]]
    draw.polygon(outback_pts, fill="#AD6A3B")
    
    # Himalayan Mountain Range (Snow + Ridge)
    himalaya_pts = [lon_lat_to_xy(lon, lat) for lon, lat in [
        (73.0, 35.0), (80.0, 32.0), (88.0, 29.0), (95.0, 29.0),
        (94.0, 27.5), (86.0, 27.5), (78.0, 30.5), (73.0, 33.5)
    ]]
    draw.polygon(himalaya_pts, fill="#DFE6ED")
    
    # Andes Mountain Crest
    andes_pts = [lon_lat_to_xy(lon, lat) for lon, lat in [
        (-76.0, 5.0), (-78.0, -5.0), (-70.0, -18.0), (-68.0, -32.0), (-70.0, -50.0),
        (-72.0, -50.0), (-71.0, -32.0), (-73.0, -18.0), (-80.0, -5.0)
    ]]
    draw.polygon(andes_pts, fill="#6E6152")
    
    # Rocky Mountains
    rockies_pts = [lon_lat_to_xy(lon, lat) for lon, lat in [
        (-125.0, 58.0), (-115.0, 50.0), (-108.0, 40.0), (-105.0, 35.0),
        (-108.0, 35.0), (-112.0, 42.0), (-118.0, 52.0), (-128.0, 58.0)
    ]]
    draw.polygon(rockies_pts, fill="#695B4E")
    
    # Alps (Europe)
    alps_pts = [lon_lat_to_xy(lon, lat) for lon, lat in [
        (6.0, 45.0), (10.0, 47.0), (14.0, 47.0), (12.0, 46.0), (7.0, 44.5)
    ]]
    draw.polygon(alps_pts, fill="#E2EBF2")
    
    # 4. Coastlines and Political Borders (Crisp definition)
    for poly, _, _ in all_landmasses:
        pixel_points = [lon_lat_to_xy(lon, lat) for lon, lat in poly]
        if len(pixel_points) > 2:
            draw.line(pixel_points + [pixel_points[0]], fill="#1B3125", width=3)
            draw.line(pixel_points + [pixel_points[0]], fill="#3A664A", width=1)
            
    # 5. Geodetic Graticule Lines (Subtle cartographic reference)
    # Parallels
    for lat in [-60, -30, 0, 30, 60]:
        y = int(((90.0 - lat) / 180.0) * (HEIGHT - 1))
        color = (56, 189, 248, 80) if lat != 0 else (56, 189, 248, 140)
        draw.line([(0, y), (WIDTH, y)], fill=color[:3], width=2 if lat == 0 else 1)
        
    # Meridians
    for lon in range(-180, 181, 30):
        x = int(((lon + 180.0) / 360.0) * (WIDTH - 1))
        color = (56, 189, 248, 80) if lon not in [0, 180, -180] else (56, 189, 248, 140)
        draw.line([(x, 0), (x, HEIGHT)], fill=color[:3], width=2 if lon == 0 else 1)

    # Save Real Earth High-Res Equirectangular Map
    map_path = os.path.join(OUTPUT_DIR, "earth_map.jpg")
    img.save(map_path, quality=95)
    print(f"[SkyGuard Earth] Saved high-resolution Earth Map Texture: {map_path}")
    
    # 6. Generate Bump/Elevation Relief Map
    print(f"[SkyGuard Earth] Generating {WIDTH}x{HEIGHT} Earth Elevation Relief Bump Map...")
    bump_img = Image.new("L", (WIDTH, HEIGHT), 25) # Deep ocean
    bump_draw = ImageDraw.Draw(bump_img)
    
    for poly, _, _ in all_landmasses:
        pts = [lon_lat_to_xy(lon, lat) for lon, lat in poly]
        if len(pts) > 2:
            bump_draw.polygon(pts, fill=110) # Plains / low elevation
            
    # Mountain elevation bumps
    bump_draw.polygon(himalaya_pts, fill=255) # Highest elevation
    bump_draw.polygon(andes_pts, fill=220)
    bump_draw.polygon(rockies_pts, fill=200)
    bump_draw.polygon(alps_pts, fill=210)
    
    bump_smoothed = bump_img.filter(ImageFilter.GaussianBlur(radius=3))
    bump_path = os.path.join(OUTPUT_DIR, "earth_bump.jpg")
    bump_smoothed.save(bump_path, quality=90)
    print(f"[SkyGuard Earth] Saved Earth Elevation Bump Map: {bump_path}")

if __name__ == "__main__":
    generate_earth_textures()
