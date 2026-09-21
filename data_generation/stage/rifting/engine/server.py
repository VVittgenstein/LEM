from __future__ import annotations
import argparse,json,math,os
from functools import lru_cache
from http.server import ThreadingHTTPServer,SimpleHTTPRequestHandler
from urllib.parse import urlsplit,parse_qs
import numpy as np
from .common import OUT,ROOT,load,stress_display
from .products import Run
from .elastic import sample_plane
from .forcing import amplitude
from .faults import geometry_at,cumulative_at
from reporting.viewer_palette import banded_colors

RUN=None
@lru_cache(maxsize=5)
def snapshot(index):
    frame=RUN.timeline['frames'][index]
    return dict(np.load(RUN.path/'frames'/(frame['frame_id']+'.npz')))

class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs):super().__init__(*args,directory=str(RUN.path),**kwargs)
    def log_message(self,*args):pass
    def json(self,value):
        body=json.dumps(value,ensure_ascii=False,allow_nan=False).encode('utf-8')
        self.send_response(200);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    def do_GET(self):
        path=urlsplit(self.path);q=parse_qs(path.query)
        if path.path=='/':
            body=(ROOT/'reporting/gallery.html').read_bytes();self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body);return
        if not path.path.startswith('/api/'):return super().do_GET()
        try:
            if path.path=='/api/config':
                self.json(dict(seed=int(RUN.path.name.replace('seed','')),length=RUN.length,solver_spacing_km=RUN.length/(RUN.basis.shape[1]-1),window=RUN.window,frames=RUN.timeline['frames'],pages=RUN.timeline['nine_panel_pages'],scales=RUN.scale,
                    palette=banded_colors()[:,:3].tolist(),fault_count=len(RUN.faults),forcing_count=len(RUN.episodes)));return
            index=int(q.get('frame',['0'])[0])
            if not 0<=index<len(RUN.timeline['frames']):raise ValueError('Frame out of range')
            frame=RUN.timeline['frames'][index];t=frame['elapsed_Myr'];data=snapshot(index)
            if path.path=='/api/state':
                faultrows=[];cum=cumulative_at(RUN.history,t)
                for i,f in enumerate(RUN.faults):
                    if f['birth_Myr']>t:continue
                    rate=float(np.max(data['slip_rates_m_per_year'][i]))
                    faultrows.append(dict(id=f['id'],active=rate>1e-10,trace=(geometry_at(f,t)-np.array(RUN.window['origin_km'])).tolist(),
                        slip_mm_per_year=rate*1000,cumulative_slip_m=float(cum[i].max()),dip_deg=f['dip_deg'],depth_km=f['bottom_depth_km'],
                        birth_Myr=f['birth_Myr'],dip_direction_rad=f['dip_direction_rad']))
                forcing=[]
                for e in RUN.episodes:
                    if e['start_Myr']>t:continue
                    strength=float(amplitude(e,t))
                    state='ended' if t>=e['natural_end_Myr'] else 'starting' if strength<=1e-8 else 'active'
                    forcing.append(dict(id=e['id'],kind=e['kind'],position=e['position_km'],direction=e['direction'],
                        force_N=strength*e['reference_force_N'],active=strength>1e-8,state=state,start_Myr=e['start_Myr'],end_Myr=e['natural_end_Myr']))
                self.json(dict(frame=frame,faults=faultrows,forcing=forcing,
                    ranges=dict(U=[float(data['U_m_per_year'].min())*1000,float(data['U_m_per_year'].max())*1000],
                        local=[float(stress_display(data['local'])[0].min()),float(stress_display(data['local'])[0].max())],
                        displacement=[float(data['displacement_m'].min()),float(data['displacement_m'].max())])));return
            if path.path=='/api/cells':
                kind=q.get('kind',['far'])[0];size=500 if kind in ['window','U','displacement'] else RUN.length
                x0=max(0,int(q.get('x0',['0'])[0]));y0=max(0,int(q.get('y0',['0'])[0]));nx=max(1,min(500,int(q.get('nx',['1'])[0]),int(size)-x0));ny=max(1,min(500,int(q.get('ny',['1'])[0]),int(size)-y0))
                if x0>=size or y0>=size:raise ValueError('Cells outside domain')
                if kind in ['U','displacement']:
                    values=data['U_m_per_year'][y0:y0+ny,x0:x0+nx]*1000 if kind=='U' else data['displacement_m'][y0:y0+ny,x0:x0+nx]
                    angles=None
                else:
                    plane=data['far'] if kind=='far' else data['local'] if kind=='local' else data['far']+data['local']
                    origin=RUN.window['origin_km'] if kind=='window' else [0,0]
                    xx,yy=np.meshgrid(np.arange(x0,x0+nx)+.5+origin[0],np.arange(y0,y0+ny)+.5+origin[1])
                    s=sample_plane(plane,xx,yy,RUN.length);values,angles=stress_display(s)
                self.json(dict(x0=x0,y0=y0,nx=nx,ny=ny,values=values.ravel().tolist(),angles=angles.ravel().tolist() if angles is not None else None));return
            self.send_error(404)
        except Exception as error:self.send_error(400,str(error))

def main():
    global RUN
    ap=argparse.ArgumentParser();ap.add_argument('--port',type=int,default=8767);ap.add_argument('--seed',type=int,default=1001);args=ap.parse_args()
    RUN=Run(args.seed)
    print(f'http://127.0.0.1:{args.port}',flush=True)
    ThreadingHTTPServer(('127.0.0.1',args.port),Handler).serve_forever()

if __name__=='__main__':main()
