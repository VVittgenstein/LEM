"""Selected cost/accuracy design values; no numerical convergence claim."""

PROFILE_ID = 'balanced_20260921'
MESH_PARAMETERS = {
    'stress_solver_nodes': 97,
    'stress_depth_layers': 5,
    'response_nodes': 65,
    'response_depth_layers': 9,
}


def apply_profile(model):
    model['design_priors'].update(MESH_PARAMETERS)
    model['numerical_profile'] = {
        'id': PROFILE_ID,
        'status': 'explicit performance/accuracy design choice',
        'convergence_claim': False,
        'stress_mesh_policy': 'fixed node budget across candidate auxiliary domains',
        'query_spacing_km': 1,
        'evidence': 'NUMERICAL_CLOSEOUT.md',
    }
    return model
