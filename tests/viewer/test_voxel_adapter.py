from __future__ import annotations
import struct
from pathlib import Path
import numpy as np
import pytest
from lem_viewer.models import TerrainChannel, TerrainDataset
from lem_viewer.voxel.adapter import prepare_display, water_level, HEADER
from lem_viewer.loaders.flem_loader import FlemLoader, HEADER as FLEM_HEADER

def dataset(shape=(3,5)):
    ds=TerrainDataset("test",shape,(2000.,1000.),metadata={"meta":{"grid":{"dx_m":1000,"dy_m":2000}}})
    ds.add_channel(TerrainChannel("elevation",units="m",kind="elevation",array=np.linspace(-100,3400,np.prod(shape)).reshape(shape)))
    ds.add_channel(TerrainChannel("drainage_area",units="m2",kind="drainage_area",transform="log10",array=np.logspace(3,9,np.prod(shape)).reshape(shape)))
    return ds

def test_height_levels_change_precision_but_preserve_physical_input(tmp_path):
    ds=dataset()
    low=prepare_display(ds,"elevation",height_levels=36)
    high=prepare_display(ds,"elevation",height_levels=72)
    assert (low.minimum,low.maximum,low.dx,low.dy,low.exaggeration)==(high.minimum,high.maximum,high.dx,high.dy,high.exaggeration)
    assert low.layer_metres==pytest.approx(100)
    assert high.layer_metres==pytest.approx(3500/71)
    assert np.array_equal(low.elevation,high.elevation)
    high.write(tmp_path/"display.bin")
    payload=(tmp_path/"display.bin").read_bytes()
    magic,nx,ny,count,flags,*physical=HEADER.unpack_from(payload)
    assert (magic,nx,ny,count)==(b"LVT1",5,3,72)
    assert physical[:4]==[1000,2000,-100,3400]
    assert len(payload)==HEADER.size+15*16

def test_non_square_stride_keeps_data_sampling_distance():
    display=prepare_display(dataset((7,11)),"elevation",max_display_size=5)
    assert display.elevation.shape==(3,4)
    assert (display.dx,display.dy)==(3000,6000)

def test_drainage_uses_the_main_logarithmic_scale():
    ds=dataset()
    ds.channels["drainage_area"].array[0,0]=0
    display=prepare_display(ds,"drainage_area",levels=8)
    assert display.transform=="log10"
    assert display.colors[0,0,3]==0
    assert np.array_equal(display.colors,display.scale.rgba(ds.get_channel("drainage_area").display_array()))
    assert not np.array_equal(display.elevation,ds.get_channel("drainage_area").array)

def test_water_data_default_override_and_explicit_dry():
    ds=dataset()
    assert water_level(ds).metres==0 and water_level(ds).source=="default"
    ds.metadata["meta"]["settings"]={"sea_level_final_m":-125}
    assert water_level(ds).metres==-125 and water_level(ds).source=="data"
    assert water_level(ds,30).metres==30 and water_level(ds,30).source=="manual"
    ds.metadata["meta"]["has_water"]=False
    assert not water_level(ds).enabled

def test_missing_fields_do_not_become_dataset_channels():
    ds=dataset()
    prepare_display(ds,"elevation",material=True)
    assert "erosion_rate" not in ds.channels

def test_invalid_values_and_holes():
    ds=dataset()
    ds.channels["elevation"].array[0,0]=np.nan
    assert np.isnan(prepare_display(ds,"elevation").elevation[0,0])
    ds.channels["elevation"].array[:]=np.nan
    with pytest.raises(ValueError,match="finite"):prepare_display(ds,"elevation")


def test_large_voxel_display_is_not_rejected_by_fixed_memory_budget():
    display=prepare_display(dataset((500,500)),"elevation",height_levels=3611)
    assert display.height_levels==3611 and display.elevation.size*(3611+4)>512*1024*1024

def test_height_unit_conversion_and_flat_surface():
    ds=dataset()
    ds.channels["elevation"].array[:]=2
    ds.channels["elevation"].units="km"
    display=prepare_display(ds,"elevation",height_levels=72)
    assert display.minimum==display.maximum==2000
    assert display.layer_metres==0

def write_flem(path: Path):
    arrays=np.arange(18,dtype="<f4").reshape(3,2,3)
    path.write_bytes(FLEM_HEADER.pack(b"FLEM",1,3,2,2000,2500,0,5,6,11,12,17,1,-20,b"\0"*8)+arrays.tobytes())
    return arrays

def test_flem_grid_orientation_channels_and_water(tmp_path):
    path=tmp_path/"地形.flem";arrays=write_flem(path)
    ds=FlemLoader().load(path)
    assert ds.spacing==(2500,1000)
    assert np.array_equal(ds.get_channel("elevation").array,arrays[0])
    assert ds.get_channel("drainage_area").transform=="log10"
    assert ds.get_channel("erosion_rate").units==""
    assert water_level(ds).metres==-20

def test_flem_truncation_and_oversized_dimensions(tmp_path):
    path=tmp_path/"bad.flem";write_flem(path)
    path.write_bytes(path.read_bytes()[:-4])
    with pytest.raises(ValueError,match="length"):FlemLoader().load(path)
    content=bytearray(path.read_bytes());struct.pack_into("<I",content,8,2**32-1);path.write_bytes(content)
    with pytest.raises(ValueError,match="dimensions"):FlemLoader().load(path)
