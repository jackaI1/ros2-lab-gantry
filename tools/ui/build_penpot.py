"""Create editable native Penpot boards, components and navigation via its API.

Only runs against the disposable CI localhost instance. Never logs credentials.
"""
import json
import secrets
import time
import uuid
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[2]
ZERO='00000000-0000-0000-0000-000000000000'
BASE='http://localhost:9001'
NS=uuid.UUID('85472f49-36b1-4a3b-9e09-32e6ebd7658a')
def uid(name):return str(uuid.uuid5(NS,name))


def create_shapes(design,file_id,page_id):
    changes=[];buttons=[]
    palette=design['tokens']
    frames={name:uid('frame '+name) for name in design['screens']+['Components']}
    def add(kind,name,x,y,w,h,frame,parent=None,fill=None,text=None,**extra):
        identifier=uid(name)
        points=[{'x':x,'y':y},{'x':x+w,'y':y},{'x':x+w,'y':y+h},{'x':x,'y':y+h}]
        obj={'id':identifier,'name':name,'type':kind,'x':x,'y':y,'width':w,'height':h,
             'selrect':{'x':x,'y':y,'width':w,'height':h,'x1':x,'y1':y,'x2':x+w,'y2':y+h},
             'points':points,'transform':{'a':1,'b':0,'c':0,'d':1,'e':0,'f':0},
             'transform-inverse':{'a':1,'b':0,'c':0,'d':1,'e':0,'f':0},
             'parent-id':parent or frame,'frame-id':frame,'rotation':0,
             'fills':[{'fill-color':fill or palette['white'],'fill-opacity':1}],**extra}
        if kind in ('frame','group'):obj['shapes']=[]
        if text is not None:
            obj['content']={'type':'root','children':[{'type':'paragraph-set','children':[
                {'type':'paragraph','children':[{'text':text,'font-id':'sourcesanspro','font-family':'sourcesanspro',
                    'font-size':str(extra.pop('size',18)),'font-weight':'400','font-variant-id':'regular','font-style':'normal','fills':obj['fills']}]}]}]}
            font_size=int(obj['content']['children'][0]['children'][0]['children'][0]['font-size'])
            obj['position-data']=[{'x':x,'y':y+font_size,'width':min(w,len(text)*font_size*.55),
                'height':font_size*1.2,'font-family':'sourcesanspro','font-size':str(font_size),
                'font-weight':'400','font-style':'normal','text':text,'fills':obj['fills']}]
            obj.pop('size',None);obj['grow-type']='fixed'
        changes.append({'type':'add-obj','id':identifier,'obj':obj,'page-id':page_id,
                        'frame-id':frame,'parent-id':parent or frame})
        return identifier
    def text(name,value,x,y,width,frame,size=18,colour=None,parent=None):
        return add('text',name,x,y,width,size*1.5,frame,parent,colour or palette['ink'],value,size=size)
    for i,name in enumerate(design['screens']+['Components']):
        x=i*540;frame=frames[name]
        # Explicit ids ensure the native navigation links survive regeneration.
        add('frame','frame '+name,x,0,480,740,ZERO,parent=ZERO,fill=palette['surface'])
        add('rect',name+' header',x,0,480,100,frame,fill=palette['ink'])
        text(name+' title',name,x+24,20,420,frame,28,palette['white'])
        text(name+' subtitle','Lab gantry / simulation',x+24,63,420,frame,16,palette['white'])
        if name != 'Components':
            add('rect',name+' persistent stop',x+368,24,96,44,frame,fill=palette['stop'],rx=6,ry=6,
                interactions=[{'event-type':'click','action-type':'navigate',
                               'destination':frames['Fault recovery'],'preserve-scroll':False}])
            text(name+' persistent stop label','Stop',x+388,30,72,frame,22,palette['white'])
            changes[-1]['obj']['interactions']=[{'event-type':'click','action-type':'navigate',
                'destination':frames['Fault recovery'],'preserve-scroll':False}]
        if name=='Components':
            text('library title','Controls I reuse',x+24,120,420,frame,24)
            for n,(label,colour) in enumerate([('Action button',palette['control']),('Stop button',palette['stop'])]):
                group=uid(label+' master');component=uid(label+' component')
                add('group',label+' master',x+24,190+n*120,432,72,frame,
                    **{'component-id':component,'component-file':file_id,'component-root':True,'main-instance':True})
                add('rect',label+' surface',x+24,190+n*120,432,72,frame,parent=group,fill=colour,rx=6,ry=6)
                text(label+' text',label,x+44,210+n*120,390,frame,22,palette['white'],parent=group)
                changes.append({'type':'add-component','id':component,'name':label,'path':'Pendant',
                                'main-instance-id':group,'main-instance-page':page_id})
            continue
        text(name+' status','Idle     X 40.0   Y 40.0   Z 10.0 mm',x+24,116,432,frame,20)
        text(name+' hint',{'Jog':'Teach mode / joint frame / 5 mm step',
            'Teach point':'Capture measured position before running',
            'Run program':'Auto mode / taught-cycle.json',
            'Fault recovery':'Stop latched. Clearing never resumes motion.'}[name],x+24,156,432,frame,16)
        actions=[a for a in design['actions'] if a['screen']==name]
        for j,action in enumerate(actions):
            y=206+j*63
            danger=action['name']=='Emergency stop'
            label='Stop button' if danger else 'Action button'
            component=uid(label+' component')
            group=add('group',action['name']+' instance',x+24,y,432,52,frame,
                **{'component-id':component,'component-file':file_id,'component-root':True,
                   'shape-ref':uid(label+' master')})
            colour=palette['stop'] if danger else palette['control']
            add('rect',action['name']+' surface',x+24,y,432,52,frame,parent=group,fill=colour,
                **{'shape-ref':uid(label+' surface')},rx=6,ry=6)
            text(action['name']+' label',action['name'],x+40,y+10,400,frame,20,palette['white'],parent=group)
            buttons.append({'action':action['name'],'shape_id':group,'payload':action})
        text(name+' prototype note','Design preview. Controls do not send motion.',x+24,650,432,frame,14)
        for n,destination in enumerate(design['screens'][:3]):
            add('rect',name+' nav '+destination,x+16+n*152,694,144,34,frame,
                fill=palette['white'],interactions=[{'event-type':'click','action-type':'navigate',
                                                    'destination':frames[destination],'preserve-scroll':False}])
            text(name+' navlabel '+destination,destination,x+24+n*152,699,134,frame,16)
            changes[-1]['obj']['interactions']=[{'event-type':'click','action-type':'navigate',
                'destination':frames[destination],'preserve-scroll':False}]
    # Component definitions must be applied before instances are validated.
    library_objects=[c for c in changes if c.get('obj',{}).get('frame-id')==frames['Components'] or c['id']==frames['Components'] or c['type']=='add-component']
    remaining=[c for c in changes if c not in library_objects]
    flow=uid('flow')
    return library_objects+remaining+[{'type':'set-flow','page-id':page_id,'id':flow,
        'params':{'id':flow,'name':'Jog, teach, run','starting-frame':frames['Jog']}}],frames,buttons


def decode_keys(value):
    # Penpot's JSON formatter uses camelCase on output and kebab-case internally.
    if isinstance(value, dict):
        return {re.sub(r'(?<!^)(?=[A-Z])', '-', k).lower():decode_keys(v) for k,v in value.items()}
    if isinstance(value, list):
        return [decode_keys(v) for v in value]
    return value


def export_url(value):
    # SSE payloads use verbose Transit even when normal RPC uses JSON.
    if isinstance(value, dict):
        value=next(iter(value.values())) if len(value)==1 else value.get('result')
    if isinstance(value, list) and len(value)==2:
        value=value[1]
    if isinstance(value,str) and value.startswith('~r'):
        value=value[2:]
    if not isinstance(value,str) or not value.startswith(BASE+'/assets/'):
        raise ValueError('Export URL must belong to the disposable Penpot instance')
    return value


def run(output):
    import requests
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    session=requests.Session()
    def rpc(command,payload=None,raw=False):
        result=session.post(BASE+'/api/rpc/command/'+command,json=payload or {},
            headers={'Accept':'application/json'},timeout=180)
        if not result.ok:
            # Validation errors contain no session secrets for these design commands.
            raise RuntimeError(f'{command}: HTTP {result.status_code}: {result.text[:2500]}')
        return result if raw else decode_keys(result.json())
    for _ in range(90):
        try:
            response=session.get(BASE+'/api/rpc/command/get-profile',timeout=2)
            if response.status_code in (200,401):break
        except requests.RequestException:pass
        time.sleep(2)
    password=secrets.token_urlsafe(24)+'Aa1!';email='pendant-ci@example.invalid'
    token=rpc('prepare-register-profile',{'fullname':'Pendant CI','email':email,'password':password})['token']
    rpc('register-profile',{'token':token})
    rpc('login-with-password',{'email':email,'password':password})
    profile=rpc('get-profile')
    team_id=profile['default-team-id'];project_id=profile['default-project-id']
    file=rpc('create-file',{'name':'Lab gantry pendant','project-id':project_id,'is-shared':True})
    file_id=file['id'];page_id=uid('pendant page')
    design=json.loads((ROOT/'tools/ui/design.json').read_text())
    changes,frames,buttons=create_shapes(design,file_id,page_id)
    rpc('update-file',{'id':file_id,'session-id':str(uuid.uuid4()),'revn':file['revn'],
        'vern':file.get('vern',0),'changes':[{'type':'add-page','id':page_id,'name':'Pendant'}]+changes})
    exported=session.post(BASE+'/api/rpc/command/export-binfile',json={
        'file-id':file_id,'include-libraries':False,'embed-assets':False},
        headers={'Accept':'text/event-stream'},timeout=180)
    exported.raise_for_status()
    url=None
    for block in exported.text.split('\n\n'):
        if 'event: end' in block:
            data=next(line[5:].strip() for line in block.splitlines() if line.startswith('data:'))
            url=export_url(json.loads(data))
    if not url:raise RuntimeError('Penpot export did not return an archive URL: '+exported.text[:1000])
    archive=session.get(url,timeout=60);archive.raise_for_status()
    (output/'pendant.penpot').write_bytes(archive.content)
    # Re-import the actual export to prove it is a usable Penpot file.
    imported=session.post(BASE+'/api/rpc/command/import-binfile',data={
        'name':'Round-trip pendant','project-id':project_id},
        files={'file':('pendant.penpot',archive.content,'application/zip')},
        headers={'Accept':'text/event-stream'},timeout=180)
    if not imported.ok:
        raise RuntimeError(f'Penpot import HTTP {imported.status_code}: {imported.text[:3000]}')
    if 'event: error' in imported.text or 'event: end' not in imported.text:
        raise RuntimeError('Penpot round-trip import failed: '+imported.text[:1500])
    from playwright.sync_api import sync_playwright
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch(headless=True)
        context=browser.new_context(viewport={'width':1180,'height':900})
        context.add_cookies([{'name':c.name,'value':c.value,'url':BASE} for c in session.cookies])
        page=context.new_page()
        try:
            page.goto(f'{BASE}/#/view?file-id={file_id}&page-id={page_id}&frame-id={frames["Jog"]}&section=interactions&zoom=fit')
            page.locator('#shape-'+uid('Jog title')+':visible').first.wait_for(timeout=60000)
            page.evaluate('document.fonts.ready')
            page.screenshot(path=str(output/'jog.png'))
            # Native prototype links should switch the displayed board.
            current='Jog'
            for name,filename in [('Teach point','teach.png'),('Run program','run.png')]:
                page.locator('#shape-'+uid(current+' navlabel '+name)+':visible').first.click()
                page.locator('#shape-'+uid(name+' title')+':visible').first.wait_for(timeout=15000)
                page.screenshot(path=str(output/filename))
                current=name
            page.locator('#shape-'+uid(current+' persistent stop label')+':visible').first.click()
            page.locator('#shape-'+uid('Fault recovery title')+':visible').first.wait_for(timeout=15000)
            page.screenshot(path=str(output/'fault.png'))
        except Exception:
            page.screenshot(path=str(output/'failure.png'))
            print('Prototype visible text:',page.locator('body').inner_text()[:1200])
            print('Prototype surfaces:',page.locator('canvas, svg').count())
            raise
        finally:
            page.close();context.close();browser.close()
    evidence={'penpot_version':'2.18.3','native_export_bytes':len(archive.content),
              'roundtrip_import':True,'screens':list(frames),'components':2,'mapped_actions':len(design['actions']),
              'clickable_flow':['Jog','Teach point','Run program'],
              'design_source':'tools/ui/design.json','screenshots':['jog.png','teach.png','run.png','fault.png']}
    (output/'penpot-evidence.json').write_text(json.dumps(evidence,indent=2)+'\n')
    print(json.dumps(evidence,indent=2))


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--output',default='artifacts/ui')
    run(parser.parse_args().output)
