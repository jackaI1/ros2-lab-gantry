import numpy as np
import pytest
from gantry_lab.inspection import board_image, calibrate, synthetic_part, inspect


@pytest.fixture(scope='module')
def calibration():
    images=[board_image([.15*np.sin(i),.2*np.cos(i),.03*i],[-40,-25,270+20*np.sin(i)]) for i in range(8)]
    return calibrate(images,board_image([0,0,0],[-40,-25,300]))


def test_camera_calibration_recovers_scale(calibration):
    assert calibration['reprojection_rms_px']<.6
    assert abs(calibration['intrinsic'][0][0]-900)<80


@pytest.mark.parametrize('defect',['good','oversize','missing_hole','rotated','absent'])
def test_labelled_defects_and_guidance(calibration,defect):
    image,label=synthetic_part(50,defect)
    result=inspect(image,calibration)
    assert result['pass']==label['acceptable'],result
    if defect=='good':
        np.testing.assert_allclose([result['guidance']['x_mm'],result['guidance']['y_mm']],
                                  np.array(label['centre_mm'])-[40,25],atol=.5)
        assert abs(result['guidance']['angle_deg']-label['angle_deg'])<1.5
    elif defect=='absent':
        assert result['guidance'] is None
    else:
        assert not result['guidance']['valid']
