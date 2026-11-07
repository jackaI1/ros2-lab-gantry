"""Planar camera calibration and dimensional inspection with JSON guidance."""
import json
from pathlib import Path
import cv2
import numpy as np

PATTERN=(9,6)
SQUARE_MM=10.
K=np.array([[900.,0,320.],[0,900.,240.],[0,0,1.]])


def board_image(rvec, tvec, seed=0):
    image=np.full((480,640),150,np.uint8)
    for y in range(-1,PATTERN[1]):
        for x in range(-1,PATTERN[0]):
            square=np.array([[x,y,0],[x+1,y,0],[x+1,y+1,0],[x,y+1,0]],float)*SQUARE_MM
            uv,_=cv2.projectPoints(square,np.array(rvec,float),np.array(tvec,float),K,None)
            cv2.fillConvexPoly(image,np.round(uv[:,0]).astype(np.int32),235 if (x+y)%2 else 20)
    image=cv2.GaussianBlur(image,(3,3),.5)
    return image


def corners(image):
    ok, found=cv2.findChessboardCornersSB(image,PATTERN,cv2.CALIB_CB_NORMALIZE_IMAGE)
    if not ok:
        raise ValueError('Checkerboard not detected; keep all inner corners visible')
    # The rendered board uses a white outer top-left square. SB may enumerate backwards.
    if found[0,0,0]>found[-1,0,0]:
        found=found[::-1].copy()
    return found.astype(np.float32)


def object_points():
    points=np.zeros((PATTERN[0]*PATTERN[1],3),np.float32)
    points[:,:2]=np.mgrid[0:PATTERN[0],0:PATTERN[1]].T.reshape(-1,2)*SQUARE_MM
    return points


def calibrate(images, reference):
    if len(images)<5:
        raise ValueError('Use at least five tilted calibration images')
    found=[corners(image) for image in images]
    rms,intrinsic,distortion,_,_=cv2.calibrateCamera([object_points()]*len(images),found,
        images[0].shape[::-1],None,None,flags=cv2.CALIB_FIX_K3)
    undistorted=cv2.undistortPoints(corners(reference),intrinsic,distortion,P=intrinsic)
    mapping,_=cv2.findHomography(undistorted,object_points()[:,:2],0)
    if mapping is None or not np.isfinite(mapping).all():
        raise ValueError('Invalid reference plane')
    return {'intrinsic':intrinsic.tolist(),'distortion':distortion.tolist(),
            'pixel_to_plane_mm':mapping.tolist(),'reprojection_rms_px':float(rms),
            'square_mm':SQUARE_MM,'plane':'same fixed work plane as reference checkerboard'}


def to_mm(points, calibration):
    uv=cv2.undistortPoints(np.asarray(points,np.float32).reshape(-1,1,2),
        np.array(calibration['intrinsic']),np.array(calibration['distortion']),
        P=np.array(calibration['intrinsic']))
    return cv2.perspectiveTransform(uv,np.array(calibration['pixel_to_plane_mm']))[:,0]


def synthetic_part(seed, defect='good'):
    rng=np.random.default_rng(seed)
    centre=np.array([40.,25.])+rng.uniform(-5,5,2)
    angle=float(rng.uniform(-8,8) if defect!='rotated' else rng.choice([-1,1])*22.)
    width=36. if defect=='oversize' else 30.
    height=20.
    image=np.full((480,640),30,np.uint8)
    radians=np.radians(angle);r=np.array([[np.cos(radians),-np.sin(radians)],[np.sin(radians),np.cos(radians)]])
    polygon=np.array([[-width/2,-height/2],[width/2,-height/2],[width/2,height/2],[-width/2,height/2]])@r.T+centre
    def pixels(xy):
        return ((np.asarray(xy)-[40,25])*3+[320,240]).round().astype(np.int32)
    if defect!='absent':
        cv2.fillConvexPoly(image,pixels(polygon),205)
        if defect!='missing_hole':
            cv2.circle(image,tuple(pixels(centre+np.array([8.,0.])@r.T)),6,30,-1)
    noise=rng.normal(0,1.2,image.shape)
    image=np.clip(image.astype(float)+noise,0,255).astype(np.uint8)
    return image, {'seed':seed,'defect':defect,'acceptable':defect=='good',
                   'centre_mm':centre.tolist(),'angle_deg':angle,'width_mm':width,'height_mm':height}


def inspect(image, calibration):
    _,binary=cv2.threshold(image,100,255,cv2.THRESH_BINARY)
    contours,hierarchy=cv2.findContours(binary,cv2.RETR_CCOMP,cv2.CHAIN_APPROX_SIMPLE)
    external=[(i,c) for i,c in enumerate(contours) if hierarchy[0,i,3]<0 and cv2.contourArea(c)>100]
    if not external:
        return {'schema':1,'pass':False,'checks':{'presence':False},'guidance':None}
    index,outline=max(external,key=lambda item:cv2.contourArea(item[1]))
    points=to_mm(outline,calibration)
    (cx,cy),(a,b),angle=cv2.minAreaRect(points.astype(np.float32))
    if a<b:
        a,b=b,a;angle+=90
    angle=(angle+90)%180-90
    # Hole must be a child contour at the expected local offset, not any dark speck.
    expected=np.array([cx,cy])+np.array([8*np.cos(np.radians(angle)),8*np.sin(np.radians(angle))])
    has_hole=False
    for i,c in enumerate(contours):
        if hierarchy[0,i,3]!=index:
            continue
        hole=to_mm(c,calibration)
        area=abs(cv2.contourArea(hole.astype(np.float32)))
        if 8<area<22 and np.linalg.norm(hole.mean(axis=0)-expected)<2:
            has_hole=True
    checks={'presence':len(external)==1,'dimension':abs(a-30)<1.0 and abs(b-20)<1.0,
            'orientation':abs(angle)<=10,'hole':has_hole}
    return {'schema':1,'pass':all(checks.values()),'checks':checks,
            'dimensions_mm':[float(a),float(b)],
            'guidance':{'x_mm':float(cx-40),'y_mm':float(cy-25),'angle_deg':float(angle),
                        'frame':'checkerboard plane, X right, Y down, angle clockwise',
                        'valid':all(checks.values())}}


def dataset(output, count=100):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    calibration_images=[board_image([.12*np.sin(i),.20*np.cos(i),.04*np.sin(2*i)],
        [-40+3*np.sin(i),-25+3*np.cos(i),270+25*np.sin(i*.7)]) for i in range(10)]
    calibration=calibrate(calibration_images,board_image([0,0,0],[-40,-25,300]))
    (output/'calibration.json').write_text(json.dumps(calibration,indent=2)+'\n')
    for i,image in enumerate(calibration_images):
        cv2.imwrite(str(output/f'checkerboard-{i}.png'),image)
    cv2.imwrite(str(output/'reference-plane.png'),board_image([0,0,0],[-40,-25,300]))
    results=[]
    defects=['good','oversize','missing_hole','rotated','absent']
    for seed in range(count):
        image,label=synthetic_part(seed,defects[seed%len(defects)])
        result=inspect(image,calibration)
        results.append({'label':label,'inspection':result})
        if seed<10:
            cv2.imwrite(str(output/f'part-{seed}.png'),image)
    good=[r for r in results if r['label']['acceptable']]
    bad=[r for r in results if not r['label']['acceptable']]
    report={'dataset':'seeded synthetic planar conveyor images; fixed camera and work height',
            'count':count,'calibration_rms_px':calibration['reprojection_rms_px'],
            'false_pass_rate':sum(r['inspection']['pass'] for r in bad)/len(bad),
            'false_fail_rate':sum(not r['inspection']['pass'] for r in good)/len(good),'results':results}
    (output/'inspection.json').write_text(json.dumps(report,indent=2)+'\n')
    return report


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--output',default='output/inspection')
    result=dataset(parser.parse_args().output)
    print(json.dumps({k:v for k,v in result.items() if k!='results'},indent=2))
