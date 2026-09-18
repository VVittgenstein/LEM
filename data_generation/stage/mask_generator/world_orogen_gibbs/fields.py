import numpy as np
from scipy.ndimage import gaussian_filter


def generate_fields(seed,settings,labels):
    # Padding is larger than the 4-sigma support, so filtering boundaries cannot
    # influence the returned center. No changes to the field during Gibbs updates.
    fields=[]
    for index,sigma in enumerate(settings.field_sigmas_km):
        padding=int(np.ceil(4*sigma))+1
        rng=np.random.default_rng(np.random.SeedSequence([seed,420,index]))
        source=rng.standard_normal((settings.size+2*padding,)*2)
        filtered=gaussian_filter(source,sigma,mode='constant',truncate=4.)
        value=filtered[padding:padding+settings.size,padding:padding+settings.size].copy()
        value-=value.mean();value/=value.std()
        fields.append(value)
    combined=np.einsum('i,iyx->yx',settings.field_weights,np.asarray(fields))
    combined-=combined.mean();combined/=combined.std()
    area=np.bincount(labels.ravel())[1:]
    average=np.bincount(labels.ravel(),weights=combined.ravel())[1:]/area
    return np.asarray(fields),combined,average
