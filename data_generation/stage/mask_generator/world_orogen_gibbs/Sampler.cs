// Exact binary conditional updates with replica exchange. Original project code.
// .NET Framework compiler is used without adding packages to the Python environment.
using System;
using System.IO;
using System.Collections.Generic;

class Pcg {
    ulong state; const ulong inc=1442695040888963407UL;
    public Pcg(uint seed) { state=0; Next(); state+=seed; Next(); }
    public uint Next() { unchecked { ulong old=state; state=old*6364136223846793005UL+inc;
        uint x=(uint)(((old>>18)^old)>>27); int r=(int)(old>>59);
        return (x>>r)|(x<<((-r)&31)); } }
    public double Uniform() { return (Next()+0.5)/4294967296.0; }
    public int Integer(int n) { uint bound=(uint)n, threshold=unchecked(0U-bound)%bound;
        uint r; do { r=Next(); } while(r<threshold); return (int)(r%bound); }
}
class State {
    public bool[] Z; public double A,X,Y,M,P,F;
    public State(int n) { Z=new bool[n]; }
}
class Update { public int Id; public bool Old,New; public double P,U,E0,E1; }
class Sampler {
    int n,chains,nt,burn,draws,thin,center; uint seed;
    double wc,wr,wp,wg,wa,soft,lo,hi;
    double[] a,x,y,m,f,degree,temps;
    bool[] allowed; int[][] neighbors; double[][] lengths; int[] eligible;
    long adds=0,removes=0;
    double Energy(double A,double X,double Y,double M,double P,double F) {
        if(A<1e-14) return Double.PositiveInfinity;
        double c=(X*X+Y*Y)/(A*A), r=M/A-c, gap=Math.Max(Math.Max(lo-A,A-hi),0);
        return wa*.5*gap*gap/(soft*soft)+wc*c+wr*r+wp*P-wg*F;
    }
    double Energy(State s) { return Energy(s.A,s.X,s.Y,s.M,s.P,s.F); }
    State Initial(int kind,Pcg rng) {
        State s=new State(n);
        if(kind%4==0) { int root=center; if(!allowed[root])root=eligible[0]; s.Z[root]=true; }
        if(kind%4==1) foreach(int i in eligible)s.Z[i]=true;
        if(kind%4==2) foreach(int i in eligible)s.Z[i]=rng.Uniform()<.5;
        if(kind%4==3) { int[] order=(int[])eligible.Clone(); Array.Sort(order,delegate(int i,int j){return (m[i]/a[i]).CompareTo(m[j]/a[j]);});
            double sum=0;foreach(int i in order) {s.Z[i]=true;sum+=a[i];if(sum>=.55)break;} }
        bool any=false;for(int i=0;i<n;i++)any|=s.Z[i];if(!any)s.Z[eligible[0]]=true;
        Recompute(s);return s;
    }
    void Recompute(State s) {
        s.A=s.X=s.Y=s.M=s.P=s.F=0;
        for(int i=0;i<n;i++)if(s.Z[i]) {
            s.A+=a[i];s.X+=x[i];s.Y+=y[i];s.M+=m[i];s.F+=f[i];
            for(int k=0;k<neighbors[i].Length;k++)if(!s.Z[neighbors[i][k]])s.P+=lengths[i][k];
        }
    }
    void Sweep(State s,double t,Pcg rng,List<Update> trace) {
        int[] order=(int[])eligible.Clone();
        for(int k=order.Length-1;k>0;k--) {int j=rng.Integer(k+1),tmp=order[k];order[k]=order[j];order[j]=tmp;}
        foreach(int i in order) {
            double shared=0;for(int j=0;j<neighbors[i].Length;j++)if(s.Z[neighbors[i][j]])shared+=lengths[i][j];
            double dp=degree[i]-2*shared;
            bool old=s.Z[i]; double sign=old?-1:1;
            double current=Energy(s), alternate=Energy(s.A+sign*a[i],s.X+sign*x[i],s.Y+sign*y[i],s.M+sign*m[i],s.P+sign*dp,s.F+sign*f[i]);
            double e0=old?alternate:current,e1=old?current:alternate;
            double v=(e1-e0)/t;
            double p=v>=0? Math.Exp(-v)/(1+Math.Exp(-v)) : 1/(1+Math.Exp(v));
            double u=rng.Uniform(); bool next=u<p;
            if(next!=old) { s.Z[i]=next;s.A+=sign*a[i];s.X+=sign*x[i];s.Y+=sign*y[i];s.M+=sign*m[i];s.P+=sign*dp;s.F+=sign*f[i];
                if(next) adds++; else removes++; }
            if(trace!=null)trace.Add(new Update {Id=i,Old=old,New=next,P=p,U=u,E0=e0,E1=e1});
        }
    }
    void WriteState(BinaryWriter w,State s,int sweep) {
        w.Write(sweep); for(int i=0;i<n;i++)w.Write((byte)(s.Z[i]?1:0));
        bool[] seen=new bool[n];double first=0,second=0;int count=0;int[] queue=new int[n];
        for(int i=0;i<n;i++) if(s.Z[i]&&!seen[i]) {
            int start=0,end=1;queue[0]=i;seen[i]=true;double mass=0;
            while(start<end) {int j=queue[start++];mass+=a[j];foreach(int k in neighbors[j])if(s.Z[k]&&!seen[k]){seen[k]=true;queue[end++]=k;}}
            count++;if(mass>first){second=first;first=mass;}else if(mass>second)second=mass;
        }
        double c=(s.X*s.X+s.Y*s.Y)/(s.A*s.A);
        foreach(double value in new double[]{Energy(s),s.A,s.X/s.A,s.Y/s.A,s.M/s.A-c,s.P,s.F,count,first/s.A,second/s.A,s.Z[center]?1:0})w.Write(value);
    }
    void Run(string input,string output) {
        using(BinaryReader r=new BinaryReader(File.OpenRead(input))) {
            if(r.ReadInt32()!=20260911)throw new Exception("input format");
            n=r.ReadInt32();chains=r.ReadInt32();nt=r.ReadInt32();burn=r.ReadInt32();draws=r.ReadInt32();thin=r.ReadInt32();seed=r.ReadUInt32();center=r.ReadInt32();
            wc=r.ReadDouble();wr=r.ReadDouble();wp=r.ReadDouble();wg=r.ReadDouble();wa=r.ReadDouble();soft=r.ReadDouble();lo=r.ReadDouble();hi=r.ReadDouble();
            temps=new double[nt];for(int k=0;k<nt;k++)temps[k]=r.ReadDouble();
            a=new double[n];x=new double[n];y=new double[n];m=new double[n];f=new double[n];degree=new double[n];allowed=new bool[n];neighbors=new int[n][];lengths=new double[n][];
            List<int> ids=new List<int>();
            for(int i=0;i<n;i++) {
                a[i]=r.ReadDouble();x[i]=r.ReadDouble();y[i]=r.ReadDouble();m[i]=r.ReadDouble();f[i]=r.ReadDouble();allowed[i]=r.ReadByte()!=0;if(allowed[i])ids.Add(i);
                int d=r.ReadInt32();neighbors[i]=new int[d];lengths[i]=new double[d];
                for(int j=0;j<d;j++){neighbors[i][j]=r.ReadInt32();lengths[i][j]=r.ReadDouble();degree[i]+=lengths[i][j];}
            }
            eligible=ids.ToArray();if(eligible.Length==0)throw new Exception("no eligible partitions");
        }
        using(BinaryWriter w=new BinaryWriter(File.Create(output))) {
            w.Write(20260912);w.Write(n);w.Write(chains);w.Write(draws);
            for(int chain=0;chain<chains;chain++) {
                Pcg rng=new Pcg(unchecked(seed+(uint)chain*1000003U));
                State[] states=new State[nt];for(int k=0;k<nt;k++)states[k]=Initial(chain,rng);
                List<State> history=new List<State>();List<int> historySweeps=new List<int>();
                long[] proposed=new long[Math.Max(0,nt-1)],accepted=new long[Math.Max(0,nt-1)];
                List<Update> lastTrace=new List<Update>(); bool[] before=null;
                int total=burn+draws*thin;
                for(int step=1;step<=total;step++) {
                    if(step==total)before=(bool[])states[0].Z.Clone();
                    for(int k=0;k<nt;k++)Sweep(states[k],temps[k],rng,step==total&&k==0?lastTrace:null);
                    if(step%4==0 && step<total)for(int k=(step/4)%2;k+1<nt;k+=2) {
                        proposed[k]++;
                        double logp=(1/temps[k]-1/temps[k+1])*(Energy(states[k])-Energy(states[k+1]));
                        if(Math.Log(rng.Uniform())<Math.Min(0,logp)){State tmp=states[k];states[k]=states[k+1];states[k+1]=tmp;accepted[k]++;}
                    }
                    if(step%64==0)foreach(State s in states)Recompute(s);
                    if(step<=burn && (step==1||step%Math.Max(1,burn/32)==0)) {
                        State copy=new State(n);copy.Z=(bool[])states[0].Z.Clone();Recompute(copy);history.Add(copy);historySweeps.Add(step);
                    }
                    if(step>burn && (step-burn)%thin==0)WriteState(w,states[0],step);
                }
                w.Write(history.Count);for(int k=0;k<history.Count;k++)WriteState(w,history[k],historySweeps[k]);
                for(int i=0;i<n;i++)w.Write((byte)(before[i]?1:0));
                w.Write(lastTrace.Count);foreach(Update u in lastTrace){w.Write(u.Id);w.Write(u.Old);w.Write(u.New);w.Write(u.P);w.Write(u.U);w.Write(u.E0);w.Write(u.E1);}
                w.Write(nt-1);for(int k=0;k+1<nt;k++){w.Write(proposed[k]);w.Write(accepted[k]);}
                Console.WriteLine("chain "+chain+" completed, retained "+draws);
            }
            w.Write(adds);w.Write(removes);
        }
    }
    static int Main(string[] args) {try{new Sampler().Run(args[0],args[1]);return 0;}catch(Exception e){Console.Error.WriteLine(e);return 1;}}
}
