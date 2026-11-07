"""Headless two-axis MuJoCo tracking task, PPO training and paired seeded evaluation."""
import json
from pathlib import Path
import gymnasium as gym
import mujoco
import numpy as np
from gymnasium import spaces

MODEL=Path(__file__).resolve().parent/'models/lamp.xml'


class LampEnv(gym.Env):
    metadata={'render_modes':[]}
    def __init__(self, randomized=False, horizon=400):
        self.model=mujoco.MjModel.from_xml_path(str(MODEL))
        self.data=mujoco.MjData(self.model)
        self.mass=self.model.body_mass.copy()
        self.inertia=self.model.body_inertia.copy()
        self.friction=self.model.dof_frictionloss.copy()
        self.damping=self.model.dof_damping.copy()
        self.randomized=randomized
        self.horizon=horizon
        self.action_space=spaces.Box(-1.,1.,shape=(2,),dtype=np.float32)
        self.observation_space=spaces.Box(-np.inf,np.inf,shape=(8,),dtype=np.float32)
        self.steps=0

    def target(self):
        t=self.steps*.02
        if t<2:
            return self.offset, np.zeros(2)
        dt=t-2
        return self.offset+self.amplitude*np.sin(self.frequency*dt), self.amplitude*self.frequency*np.cos(self.frequency*dt)

    def observation(self):
        target,velocity=self.target()
        return np.concatenate((self.data.qpos,self.data.qvel,target-self.data.qpos,velocity)).astype(np.float32)

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        mujoco.mj_resetData(self.model,self.data)
        self.steps=0
        self.offset=self.np_random.uniform(-.45,.45,2)
        self.amplitude=self.np_random.uniform(.15,.3,2)
        self.frequency=self.np_random.uniform(.6,1.4,2)
        mass_scale=float(self.np_random.uniform(.65,1.5)) if self.randomized else 1.
        friction_scale=float(self.np_random.uniform(.5,2.)) if self.randomized else 1.
        self.model.body_mass[:]=self.mass*mass_scale
        self.model.body_inertia[:]=self.inertia*mass_scale
        self.model.dof_frictionloss[:]=self.friction*friction_scale
        self.model.dof_damping[:]=self.damping*friction_scale
        mujoco.mj_setConst(self.model,self.data)
        mujoco.mj_forward(self.model,self.data)
        return self.observation(),{'mass_scale':mass_scale,'friction_scale':friction_scale}

    def step(self, action):
        action=np.asarray(action,dtype=float)
        if action.shape!=(2,) or not np.isfinite(action).all():
            raise ValueError('Expected two finite motor commands')
        action=np.clip(action,-1,1)
        self.data.ctrl[:]=action*.2
        for _ in range(4):
            mujoco.mj_step(self.model,self.data)
        self.steps+=1
        target,_=self.target()
        error=self.data.qpos-target
        # Reward is always in [0,1], with a small torque penalty.
        reward=float(np.clip(np.exp(-5*np.mean(error**2))-.01*np.mean(action**2),0,1))
        return self.observation(),reward,False,self.steps>=self.horizon,{
            'error_rad':float(np.sqrt(np.mean(error**2))), 'time_s':self.steps*.02}


def rollout(env, controller, seed):
    obs,domain=env.reset(seed=seed)
    errors=[]
    for _ in range(env.horizon):
        obs,reward,_,done,info=env.step(controller(obs))
        errors.append(info['error_rad'])
        if done:
            break
    # Settling: first 0.2 s continuously below 0.04 rad during initial 2 s step.
    settling=2.
    settled=False
    for i in range(90):
        if max(errors[i:i+10])<.04:
            settling=(i+1)*.02;settled=True;break
    return {'seed':seed,'rmse_rad':float(np.sqrt(np.mean(np.square(errors)))),
            'settling_s':settling,'settled':settled,'errors_rad':errors,**domain}


def pd(kp=.8,kd=.1):
    return lambda obs: np.clip((kp*obs[4:6]+kd*(obs[6:8]-obs[2:4]))/.2,-1,1)


def interval(values, seed=3):
    values=np.asarray(values,float)
    rng=np.random.default_rng(seed)
    means=rng.choice(values,(2000,len(values)),replace=True).mean(axis=1)
    return {'mean':float(values.mean()),'ci95':[float(x) for x in np.quantile(means,[.025,.975])]}


def train_and_evaluate(output, steps=200000, seeds=20):
    import torch
    from stable_baselines3 import PPO
    torch.set_num_threads(1)
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    env=LampEnv(randomized=True)
    model=PPO('MlpPolicy',env,seed=17,n_steps=512,batch_size=128,n_epochs=6,
        learning_rate=.0003,policy_kwargs={'net_arch':[64,64]},verbose=0,device='cpu')
    initial=rollout(LampEnv(),lambda o:model.predict(o,deterministic=True)[0],700)
    model.learn(total_timesteps=steps)
    model.save(output/'ppo-lamp')
    # Tuning uses seeds disjoint from final evaluation, under nominal physics.
    tuned=[]
    for kp in (.4,.8,1.2):
        for kd in (.05,.1,.15):
            scores=[rollout(LampEnv(),pd(kp,kd),s)['rmse_rad'] for s in range(1000,1004)]
            tuned.append((float(np.mean(scores)),kp,kd))
    _,kp,kd=min(tuned)
    result={'training_seed':17,'training_steps':int(model.num_timesteps),
            'requested_steps':steps,'eval_seeds':list(range(2000,2000+seeds)),
            'pd_gains':{'kp':kp,'kd':kd},'pd_tuning_seeds':list(range(1000,1004)),
            'untrained_seed700_rmse_rad':initial['rmse_rad'],
            'trained_seed700_rmse_rad':rollout(LampEnv(),lambda o:model.predict(o,deterministic=True)[0],700)['rmse_rad'],
            'domains':{}}
    for randomized in (False,True):
        domain='randomized' if randomized else 'nominal'
        runs={}
        for name,controller in [('pd',pd(kp,kd)),('ppo',lambda o:model.predict(o,deterministic=True)[0])]:
            trials=[rollout(LampEnv(randomized=randomized),controller,s) for s in result['eval_seeds']]
            runs[name]={'rmse_rad':interval([t['rmse_rad'] for t in trials]),
                        'settling_s':interval([t['settling_s'] for t in trials]),
                        'settled_fraction':sum(t['settled'] for t in trials)/seeds,'trials':trials}
        runs['paired_ppo_minus_pd_rmse_rad']=interval([
            a['rmse_rad']-b['rmse_rad'] for a,b in zip(runs['ppo']['trials'],runs['pd']['trials'])])
        result['domains'][domain]=runs
    result['domain_degradation_rad']={name:result['domains']['randomized'][name]['rmse_rad']['mean']-
        result['domains']['nominal'][name]['rmse_rad']['mean'] for name in ('pd','ppo')}
    (output/'evaluation.json').write_text(json.dumps(result,indent=2)+'\n')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,2,figsize=(10,4))
    for ax,domain in zip(axes,('nominal','randomized')):
        for name in ('pd','ppo'):
            errors=np.array([t['errors_rad'] for t in result['domains'][domain][name]['trials']])
            ax.plot(np.arange(errors.shape[1])*.02,errors.mean(axis=0),label=name.upper())
        ax.set(title=domain,xlabel='Time (s)',ylabel='Mean joint tracking error (rad)');ax.legend()
    fig.tight_layout();fig.savefig(output/'tracking.png');plt.close(fig)
    return result


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--output',default='output/lamp')
    parser.add_argument('--steps',type=int,default=200000);parser.add_argument('--seeds',type=int,default=20)
    args=parser.parse_args()
    result=train_and_evaluate(args.output,args.steps,args.seeds)
    print(json.dumps({k:v for k,v in result.items() if k!='domains'},indent=2))
