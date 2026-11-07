import json
import numpy as np
import pytest
import torch
from PIL import Image
from gantry_lab.pose_learning import rotation6d, add_error, validate_dataset, PoseNet


def test_pose_geometry_and_continuous_rotation():
    rotation=rotation6d(torch.tensor([1.,0,0,0,1,0])).numpy()
    np.testing.assert_allclose(rotation,np.eye(3))
    points=np.array([[0.,0,0],[1,0,0],[0,1,0]])
    assert add_error(points,rotation,[0,0,1],rotation,[0,0,1])==0
    assert add_error(points,rotation,[.01,0,1],rotation,[0,0,1])==pytest.approx(.01)
    r=rotation6d(torch.tensor([.5,.2,.3,-.2,.7,.1])).numpy()
    np.testing.assert_allclose(r.T@r,np.eye(3),atol=1e-6)
    assert np.linalg.det(r)==pytest.approx(1,abs=1e-6)
    fallback=rotation6d(torch.zeros(6)).numpy()
    np.testing.assert_allclose(fallback.T@fallback,np.eye(3))
    assert np.linalg.det(fallback)==pytest.approx(1)


def test_dataset_rejects_bad_rotation_and_leaked_seed(tmp_path):
    image=Image.new('RGB',(96,96),(30,30,30))
    image.paste((200,200,200),(20,20,70,70));image.save(tmp_path/'rgb.png')
    Image.new('L',(96,96),255).save(tmp_path/'mask.png')
    record={'seed':1,'image':'rgb.png','mask':'mask.png','rotation':np.eye(3).tolist(),
            'translation_m':[0,0,.65],'split':'narrow'}
    metadata={'version':1,'records':[record]}
    (tmp_path/'dataset.json').write_text(json.dumps(metadata))
    assert len(validate_dataset(tmp_path)['records'])==1
    metadata['records'].append(dict(record,split='heldout'))
    (tmp_path/'dataset.json').write_text(json.dumps(metadata))
    with pytest.raises(ValueError,match='disjoint'):
        validate_dataset(tmp_path)
    metadata['records']=[dict(record,rotation=np.zeros((3,3)).tolist())]
    (tmp_path/'dataset.json').write_text(json.dumps(metadata))
    with pytest.raises(ValueError,match='orthonormal'):
        validate_dataset(tmp_path)


def test_network_training_changes_weights():
    torch.manual_seed(2)
    model=PoseNet();optimizer=torch.optim.Adam(model.parameters())
    image=torch.rand(2,3,96,96);target=torch.ones(2,9)
    before=model.layers[-1].weight.detach().clone()
    loss=torch.nn.functional.mse_loss(model(image),target)
    loss.backward();optimizer.step()
    assert not torch.equal(before,model.layers[-1].weight)
    assert torch.isfinite(loss)



def test_blank_render_is_rejected_before_training(tmp_path):
    Image.new('RGB',(96,96),(0,0,0)).save(tmp_path/'rgb.png')
    Image.new('L',(96,96),255).save(tmp_path/'mask.png')
    record={'seed':1,'image':'rgb.png','mask':'mask.png','rotation':np.eye(3).tolist(),
            'translation_m':[0,0,.65],'split':'narrow'}
    (tmp_path/'dataset.json').write_text(json.dumps({'version':1,'records':[record]}))
    with pytest.raises(ValueError,match='contrast'):
        validate_dataset(tmp_path)
