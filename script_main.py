

import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
import matplotlib.pyplot as plt



# Open lat/lon text file
def OpenCoords(coords_filename):
    with open(coords_filename) as d:
        data = d.readlines()
    return data


# Create points and 4ft buffers from lat/lon
def Buffer(data):
    start = 0
    point_dict = {}

    while start < len(data):
        end = start + 8
        point = data [start:end-1]
        k = point[0].strip('.\n')
        lat = float(point[3].strip('\n').split(':')[1].strip())
        lon = float(point[4].strip('\n').split(':')[1].strip())
        v_tup = (lon,lat)
        point_dict[k] = Point(v_tup)
        start = end

    point_gdf = gpd.GeoDataFrame.from_dict(point_dict,'index')
    point_gdf.columns = ['geometry']
    point_gdf.crs = "+init=epsg:4326"
    point_gdf = point_gdf.to_crs("+init=epsg:2263")

    bfr_gs = point_gdf.buffer(4)
    bfr_gs.name = 'geometry'
    bfr_gdf = gpd.GeoDataFrame(bfr_gs, crs="+init=epsg:4326", geometry=bfr_gs.geometry)
    bfr_gdf = bfr_gdf.to_crs("+init=epsg:2263")
    return bfr_gdf


# Open attribute data and align indices
def Attributes(att_filename):
    att = pd.read_csv(att_filename)
    att.index+=1
    att.index = att.index[::-1]
    att.index = att.index.astype(str)
    return att


# Merge attributes to geometries
def MergeSHP(att_gdf, geom_gdf):
    cams_gdf = gpd.GeoDataFrame(pd.merge(att_gdf,geom_gdf,left_index=True,right_index=True))
    return cams_gdf


# Open shapefile
def OpenSHP(shp_filename):
    shp = gpd.read_file(shp_filename)
    shp = shp.to_crs("+init=epsg:2263")
    return shp


# Erase buildings from buffers to get field of view (fov)
def FOV(cams_gdf, bldgs):
    fov_gdf = gpd.overlay(cams_gdf, bldgs, how='difference')
    fov_gdf.crs = cams_gdf.crs
    return fov_gdf


# Input coordinates, attributes, and buildings for field of view (fov)
def InputData(coords_filepath, att_filepath, bldgs):
    coords = OpenCoords(coords_filepath)
    bfr = Buffer(coords)
    att = Attributes(att_filepath)
    merge = MergeSHP(att, bfr)
    fov_ovr = FOV(merge, bldgs)
    fov_col_list = fov_ovr.columns[fov_ovr.notna().any()].tolist()
    fov = fov_ovr[fov_col_list]
    fov.crs = bfr.crs
    return fov


# Intersect zones to FOVs to count them and find their total coverage area within the zone
def ZoneFOV(nbrhd_zn, nbrhd_fov):
    nbrhd_znfov = gpd.overlay(nbrhd_zn, nbrhd_fov, how='intersection')
    nbrhd_znfov.crs = nbrhd_zn.crs
    nbrhd_znfov['fov_area'] = nbrhd_znfov.area
    nbrhd_znfov['fov_cnt'] = nbrhd_znfov.shape[0]
    nbrhd_znfov['totfov_area'] = nbrhd_znfov.fov_area.sum()
    return nbrhd_znfov


# Filter for all low Quality of View (QOV) conditions, find their total non-coverage
# area within the zone, and the percentage of cams not working and area not covered
def ZoneQOV(nbrhd_zn_totcvrg):
    full_cvrg = nbrhd_zn_totcvrg.loc[nbrhd_zn_totcvrg.index.tolist(),:]
    dark = full_cvrg.loc[(full_cvrg.loc[full_cvrg.led == 'none'].index.tolist()),:]
    dark = dark.loc[(dark.loc[(dark.well_lit == 'no') | (dark.well_lit.isnull() == True)].index.tolist()),:]
    scaf = full_cvrg.loc[(full_cvrg.loc[full_cvrg.scaffoldin == 'yes'].index.tolist()),:]
    folg = full_cvrg.loc[(full_cvrg.loc[full_cvrg.foliage == 'yes'].index.tolist()),:]

    def LowQOV (low_qov, note):
        low_qov['lo_qov'] = note
        low_qov['loqov_cnt'] = low_qov.shape[0]
        low_qov['loqov_area'] = low_qov.area.sum()
        return low_qov

    dark_cvrg = LowQOV(dark, 'dark')
    scaf_cvrg = LowQOV(scaf, 'sign/scaffolding')
    folg_cvrg = LowQOV(folg, 'foliage')

    qov_cvrg = dark_cvrg.append(scaf_cvrg.append(folg_cvrg))
    qov_cvrg = qov_cvrg.loc[qov_cvrg.index.duplicated() == False]
    qov_cvrg['totqov_cnt'] = qov_cvrg.loqov_cnt.unique().sum()
    qov_cvrg['totqov_area'] = qov_cvrg.loqov_area.unique().sum()
    qov_cvrg['NoIRpct'] = (qov_cvrg.totqov_cnt/qov_cvrg.fov_cnt)*100
    qov_cvrg['actlFOV'] = ((full_cvrg.totfov_area - qov_cvrg.totqov_area)/qov_cvrg.totfov_area)*100

    zn_cvrg = full_cvrg.assign(**pd.DataFrame(columns=qov_cvrg.columns[-7:].tolist()))
    zn_cvrg.update(qov_cvrg)
    ir_df = zn_cvrg[zn_cvrg.columns[-4:].tolist()].fillna(method='ffill').fillna(method='bfill').fillna(0)
    zn_cvrg.update(ir_df)
    return zn_cvrg


### Long Island City, Queens

# Open shapefiles of selected zones and buildings of neighborhood
qn1_bldgs = OpenSHP('qn1/qn1_bldgs/qn1_bldgs.shp')
qn1_r = OpenSHP('qn1/qn1_r/qn1_r.shp')
qn1_c = OpenSHP('qn1/qn1_c/qn1_c.shp')
qn1_m = OpenSHP('qn1/qn1_m/qn1_m.shp')

# Input data for each trip
qn1_1_fov = InputData('qn1/qn1_1.txt','qn1/qn1_1_att.csv',qn1_bldgs)
qn1_2_fov = InputData('qn1/qn1_2.txt','qn1/qn1_2_att.csv',qn1_bldgs)

# Merge trips
qn1_fov = qn1_1_fov.append(qn1_2_fov,ignore_index=True)

# Find coverage for each zone
qn1_r_cvrg = ZoneQOV(ZoneFOV(qn1_r, qn1_fov))
qn1_c_cvrg = ZoneQOV(ZoneFOV(qn1_c, qn1_fov))
qn1_m_cvrg = ZoneQOV(ZoneFOV(qn1_m, qn1_fov))

# Merge zones for full neighborhood good/bad coverage
qn1_cvrg = qn1_r_cvrg.append(qn1_c_cvrg.append(qn1_m_cvrg,ignore_index=True),ignore_index=True)

# Save shapefile in a directory
qn1_cvrg.to_file('qn1/qn1_cvrg')


### Woodside, Queens

# Open shapefiles of selected zones and buildings of neighborhood
qn2_bldgs = OpenSHP('qn/qn2_bldgs/qn2_bldgs.shp')
qn2_r = OpenSHP('qn2/qn2_r/qn2_r.shp')
qn2_c = OpenSHP('qn2/qn2_c/qn2_c.shp')
qn2_m = OpenSHP('qn2/qn2_m/qn2_m.shp')

# Input data for each trip
qn2_1_fov = InputData('qn2/qn2_1.txt','qn2/qn2_1_att.csv',qn2_bldgs)
qn2_2_fov = InputData('qn2/qn2_2.txt','qn2/qn2_2_att.csv',qn2_bldgs)
qn2_3_fov = InputData('qn2/qn2_3.txt','qn2/qn2_3_att.csv',qn2_bldgs)

# Merge trips
qn2_fov = qn2_1_fov.append(qn2_2_fov.append(qn2_3_fov,ignore_index=True),ignore_index=True)

# Find coverage for each zone
qn2_r_cvrg = ZoneQOV(ZoneFOV(qn2_r, qn2_fov))
qn2_c_cvrg = ZoneQOV(ZoneFOV(qn2_c, qn2_fov))
qn2_m_cvrg = ZoneQOV(ZoneFOV(qn2_m, qn2_fov))

# Merge zones for full neighborhood good/bad coverage
qn2_cvrg = qn2_r_cvrg.append(qn2_c_cvrg.append(qn2_m_cvrg,ignore_index=True),ignore_index=True)

# Save shapefile in a directory
qn2_cvrg.to_file('qn2/qn2_cvrg')


### Williamsburg, Brooklyn

# Open shapefiles of selected zones and buildings of neighborhood
bk1_bldgs = OpenSHP('bk1/bk1_bldgs/bk1_bldgs.shp')
bk1_r = OpenSHP('bk1/bk1_r/bk1_r.shp')
bk1_c = OpenSHP('bk1/bk1_c/bk1_c.shp')
bk1_m = OpenSHP('bk1/bk1_m/bk1_m.shp')

# Input data for each trip
bk1_1_fov = InputData('bk1/bk1_1.txt','bk1/bk1_1_att.csv',bk1_bldgs)
bk1_2_fov = InputData('bk1/bk1_2.txt','bk1/bk1_2_att.csv',bk1_bldgs)

# Merge trips
bk1_fov = bk1_1_fov.append(bk1_2_fov,ignore_index=True)

# Find coverage for each zone
bk1_r_cvrg = ZoneQOV(ZoneFOV(bk1_r, bk1_fov))
bk1_c_cvrg = ZoneQOV(ZoneFOV(bk1_c, bk1_fov))
bk1_m_cvrg = ZoneQOV(ZoneFOV(bk1_m, bk1_fov))

# Merge zones for full neighborhood good/bad coverage
bk1_cvrg = bk1_r_cvrg.append(bk1_c_cvrg.append(bk1_m_cvrg,ignore_index=True),ignore_index=True)

# Save shapefile in a directory
bk1_cvrg.to_file('bk1/bk1_cvrg')
