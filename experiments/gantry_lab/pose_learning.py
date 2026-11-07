"""Train a small image-to-pose network; report ADD errors and nuisance failures."""
import json
from pathlib import Path
import numpy as np
from PIL import Image
import torch
from torch import nn
from torch.utils.data import Dataset, DataLoader


def rotation6d(value):
    a=value[...,:3];b=value[...,3:6]
    x=torch.nn.functional.normalize(a,dim=-1,eps=1e-6)
    y=torch.nn.functional.normalize(b-(x*b).sum(-1,keepdim=True)*x,dim=-1,eps=1e-6)
    z=torch.linalg.cross(x,y,dim=-1)
    return torch.stack((x,y,z),dim=-1)


def add_error(points, rotation, translation, true_rotation, true_translation):
    predicted=np.asarray(points)@np.asarray(rotation).T+translation
    truth=np.asarray(points)@np.asarray(true_rotation).T+true_translation
    return float(np.linalg.norm(predicted-truth,axis=1).mean())


def validate_dataset(root):
    root=Path(root);metadata=json.loads((root/'dataset.json').read_text())
    if metadata.get('version')!=1 or not metadata.get('records'):
        raise ValueError('Missing version 1 pose records')
    seeds=set()
    for record in metadata['records']:
        if record['seed'] in seeds:
            raise ValueError('Dataset splits must have disjoint seeds')
        seeds.add(record['seed'])
        r=np.array(record['rotation']);t=np.array(record['translation_m'])
        if r.shape!=(3,3) or t.shape!=(3,) or not np.isfinite(t).all() or t[2]<=0:
            raise ValueError('Invalid object-to-camera pose')
        if not np.allclose(r.T@r,np.eye(3),atol=1e-5) or not np.isclose(np.linalg.det(r),1,atol=1e-5):
            raise ValueError('Rotation must be right-handed and orthonormal')
        for key in ('image','mask'):
            path=(root/record[key]).resolve()
            if not path.is_relative_to(root.resolve()):
                raise ValueError('Dataset path escapes root')
            with Image.open(path) as image:
                if image.size!=(96,96):
                    raise ValueError('Expected 96x96 render and mask')
        with Image.open(root/record['mask']) as mask:
            if np.asarray(mask).max()==0:
                raise ValueError('Part mask is empty')
    return metadata


class PoseDataset(Dataset):
    def __init__(self,root,metadata,split):
        self.root=Path(root)
        self.records=[r for r in metadata['records'] if r['split']==split]
        self.images=[];self.targets=[]
        for r in self.records:
            image=np.asarray(Image.open(self.root/r['image']).convert('RGB'),np.float32)/255
            self.images.append(torch.from_numpy(image.transpose(2,0,1).copy()))
            rotation=np.array(r['rotation'])
            translation=(np.array(r['translation_m'])-[0,0,.65])/.1
            self.targets.append(torch.tensor(np.r_[rotation[:,0],rotation[:,1],translation],dtype=torch.float32))
    def __len__(self):return len(self.records)
    def __getitem__(self,index):return self.images[index],self.targets[index]


class PoseNet(nn.Module):
    def __init__(self):
        super().__init__()
        self.layers=nn.Sequential(nn.Conv2d(3,16,5,stride=2,padding=2),nn.ReLU(),
            nn.Conv2d(16,32,3,stride=2,padding=1),nn.ReLU(),
            nn.Conv2d(32,48,3,stride=2,padding=1),nn.ReLU(),nn.AdaptiveAvgPool2d((4,4)),
            nn.Flatten(),nn.Linear(48*4*4,64),nn.ReLU(),nn.Linear(64,9))
    def forward(self,image):return self.layers(image)


def experiment(dataset,output,epochs=80):
    torch.set_num_threads(1)
    metadata=validate_dataset(dataset)
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    heldout=PoseDataset(dataset,metadata,'heldout')
    results={}
    for split in ('narrow','wide'):
        torch.manual_seed(23)
        train=PoseDataset(dataset,metadata,split)
        generator=torch.Generator().manual_seed(23)
        loader=DataLoader(train,batch_size=16,shuffle=True,generator=generator)
        model=PoseNet();optimizer=torch.optim.Adam(model.parameters(),lr=.001)
        losses=[]
        for epoch in range(epochs):
            model.train();total=0.
            for image,target in loader:
                prediction=model(image)
                loss=nn.functional.mse_loss(prediction[:,:6],target[:,:6])+2*nn.functional.mse_loss(prediction[:,6:],target[:,6:])
                optimizer.zero_grad();loss.backward();optimizer.step()
                total+=loss.item()*len(image)
            losses.append(total/len(train))
        torch.save(model.state_dict(),output/f'{split}-pose.pt')
        model.eval();trials=[]
        with torch.no_grad():
            for (image,target),record in zip(heldout,heldout.records):
                prediction=model(image[None])[0]
                rotation=rotation6d(prediction[:6]).numpy()
                translation=prediction[6:].numpy()*.1+[0,0,.65]
                error=add_error(metadata['model_points_m'],rotation,translation,record['rotation'],record['translation_m'])
                trials.append({'seed':record['seed'],'lighting':record['lighting'],
                    'occlusion':record['occlusion'],'add_m':error,'success':error<.02})
        groups={}
        for key in ('lighting','occlusion'):
            for value in sorted({r[key] for r in trials}):
                selected=[r for r in trials if r[key]==value]
                groups[f'{key}:{value}']={'count':len(selected),'mean_add_m':float(np.mean([r['add_m'] for r in selected])),
                    'failure_rate':sum(not r['success'] for r in selected)/len(selected)}
        results[split]={'train_count':len(train),'heldout_count':len(heldout),'epochs':epochs,
            'training_seed':23,'loss_history':losses,'mean_add_m':float(np.mean([r['add_m'] for r in trials])),
            'success_rate':sum(r['success'] for r in trials)/len(trials),'by_condition':groups,'trials':trials}
    result={'dataset':'Blender CPU renders; no real-camera validation',
            'metric':'ADD: mean corresponding model-point distance after estimated vs true pose',
            'success_threshold_m':.02,'comparison':results}
    (output/'pose-evaluation.json').write_text(json.dumps(result,indent=2)+'\n')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,2,figsize=(9,4))
    for split in results:
        axes[0].plot(results[split]['loss_history'],label=split)
    axes[0].set(xlabel='Epoch',ylabel='Training loss');axes[0].legend()
    axes[1].boxplot([[r['add_m']*1000 for r in results[s]['trials']] for s in results],tick_labels=list(results))
    axes[1].set(ylabel='Held-out ADD (mm)')
    fig.tight_layout();fig.savefig(output/'pose-comparison.png');plt.close(fig)
    return result


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('dataset');parser.add_argument('--output',default='output/pose')
    parser.add_argument('--epochs',type=int,default=80);args=parser.parse_args()
    result=experiment(args.dataset,args.output,args.epochs)
    print(json.dumps({k:{a:b for a,b in v.items() if a not in ('trials','loss_history')} for k,v in result['comparison'].items()},indent=2))
