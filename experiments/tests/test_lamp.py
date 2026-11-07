import numpy as np
import pytest
from gantry_lab.lamp import LampEnv, rollout, pd


def test_reset_shape_reward_bounds_and_episode_limit():
    env=LampEnv(horizon=10)
    obs,_=env.reset(seed=1)
    assert obs.shape==(8,) and obs.dtype==np.float32
    for i in range(10):
        obs,reward,terminated,truncated,info=env.step([5,-5])
        assert 0<=reward<=1 and not terminated
        assert truncated==(i==9)
        assert np.isfinite(info['error_rad'])
    np.testing.assert_allclose(env.reset(seed=1)[0][:4],0)
    with pytest.raises(ValueError):
        env.step([np.nan,0])


def test_fixed_seed_domain_randomization_is_deterministic():
    env=LampEnv(randomized=True)
    first,domain=env.reset(seed=42)
    trajectory=[env.step([.1,-.2])[0] for _ in range(20)]
    second,domain2=env.reset(seed=42)
    np.testing.assert_array_equal(first,second)
    assert domain==domain2 and domain['mass_scale']!=1
    for expected in trajectory:
        np.testing.assert_allclose(env.step([.1,-.2])[0],expected,atol=1e-7)
    assert env.reset(seed=43)[1]!=domain


def test_joint_range_is_radians_and_pd_can_reach_a_target():
    env=LampEnv()
    np.testing.assert_allclose(env.model.jnt_range,[[-1.2,1.2],[-1.2,1.2]])
    trial=rollout(env,pd(1.2,.1),2001)
    assert trial['rmse_rad']<.1
    assert trial['settled']
