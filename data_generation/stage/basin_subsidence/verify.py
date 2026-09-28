"""Saved arrays, source ownership, geometry, time integrals and display contracts."""
import re
import ast
import numpy as np
from .common import *
from .schedule import Event, BasinSchedule
from .temporal import simulate

def write_manifest(output, batch):
    paths = [p for p in ROOT.iterdir() if p.is_file() and p.suffix in ('.py', '.md', '.ps1')]
    paths += [p for folder in (MODELS, SOURCES) for p in folder.rglob('*') if p.is_file()]
    paths += [p for p in output.iterdir() if p.is_file() and p.name != 'manifest.json']
    for world in batch['worlds']:
        directory = output/f"seed{world['seed']}"
        paths += [p for p in directory.iterdir() if p.is_file()]
        for event in world['events']:
            paths += [p for p in (directory/f"event{event['event_index']:02d}").iterdir() if p.is_file()]
    save(output/'manifest.json', dict(files=[dict(path=p.relative_to(ROOT).as_posix(), sha256=sha(p), bytes=p.stat().st_size)
        for p in sorted(set(paths))], source_manifest_sha256=sha(SOURCES/'manifest.json')))


def audit(output=OUT, require_figures=True):
    output = Path(output); batch = load(output/'batch.json')
    save(output/'audit.json', dict(status='running'))
    checks, event_results = [], []
    manifest = load(SOURCES/'manifest.json')
    for row in manifest['files']:
        checks.append(dict(check='frozen source unchanged', path=row['copy'], passed=sha(SOURCES/row['copy']) == row['sha256'] == sha(row['original'])))
    for row in manifest['bases']:
        checks.append(dict(check='existing base unchanged', seed=row['seed'], passed=sha(row['path']) == row['sha256']))
    geometry_hashes = []
    all_links = []
    for row in batch['events']:
        p = output/f"seed{row['seed']}/event{row['event_index']:02d}"
        full, window = Event(p, 'complete'), Event(p)
        event = full.history.event
        native = np.load(p/'native_frames.npz'); frames = load(p/'frames.json'); selection = load(p/'selection.json')
        source = np.load(p/'reference.npz'); cropped = np.load(p/'window.npz')
        t0, t1 = event['start_sim_Myr'], min(48., event['natural_end_sim_Myr'])
        a, b, c = t0, t0+(t1-t0)*.371, t1
        integral = full.history.displacement(a, c)
        split = full.history.displacement(a, b)+full.history.displacement(b, c)
        integration_error = float(np.max(abs(integral-split)))
        corners = np.array(selection['corners_source_km'])
        rotation = np.array(selection['rotation_matrix'])
        corner_lengths = np.linalg.norm(np.diff(corners, axis=0), axis=1)
        x, y = np.meshgrid(np.arange(500)+.5, np.arange(500)+.5)
        positions = (np.column_stack([x.ravel(), y.ravel()])-250)@rotation.T+np.array(selection['center_source_km'])
        sample = np.arange(0, 250000, 997)
        t = (a+c)/2
        point_values = full.at_points(positions[sample], t*1e6)
        cropped_values = window.at_time(t*1e6).ravel()[sample]
        frame_error = 0.
        for i, frame in enumerate(frames):
            expected = full.at_time(frame['sim_Myr']*1e6)
            frame_error = max(frame_error, float(np.max(abs(expected-native['u_m_per_yr'][i]))))
        repeat = full.at_time(t*1e6)
        _ = full.at_time(a*1e6)
        repeat_error = float(np.max(abs(repeat-full.at_time(t*1e6))))
        mapping_error = float(np.max(abs(point_values-cropped_values)))
        local = [
            ('finite arrays', bool(np.isfinite(native['u_m_per_yr']).all() and np.isfinite(integral).all())),
            ('complete zero boundary', bool(not np.any(source['u_m_per_yr'][[0, -1]]) and not np.any(source['u_m_per_yr'][:, [0, -1]]))),
            ('fixed 500 km window', bool(np.allclose(corner_lengths, 500, rtol=0, atol=1e-8))),
            ('rigid coordinate transform', bool(np.allclose(rotation.T@rotation, np.eye(2), atol=1e-12))),
            ('window reads original field', mapping_error < 1e-12),
            ('query does not redraw', repeat_error == 0),
            ('integral additivity', integration_error < 1e-7),
            ('frame arrays agree with evaluator', frame_error < 1e-9),
            ('no future display', all(f['sim_Myr'] <= 48 for f in frames)),
            ('modern retained when active', not event['ongoing_at_modern'] or frames[-1]['modern']),
            ('natural lifetime unchanged', abs(event['natural_end_sim_Myr']-event['start_sim_Myr']-event['duration_Myr']) < 1e-10),
            ('sampling diagnostic', row['sampling_diagnostics']['passed']),
            ('complete support independent of artificial boundary', row['minimum_active_mesh_layer'] > load(MODELS/'design.json')['boundary_layers']),
            ('natural event net downward motion', row['natural_mean_node_displacement_m'] < 0),
        ]
        with np.load(BASES/f"seed{row['seed']}/base.npz") as data:
            local.append(('pink mask identity', bool(np.array_equal(cropped['pink_overlap'], data['mask'] & cropped['support']))))
        if 'version' in selection:
            from .window import gate, candidate_metrics, selection_probabilities, weight_terms
            from .sampling_geometry import FullSupport, platform, rotation as make_rotation, window_polygon
            from .sampling_diagnostics import read_candidates
            field, land = FullSupport(p), platform(row['seed'])
            measured = candidate_metrics(field, land, np.array(selection['center_source_km']), rotation, selection['design'])
            rows = read_candidates(p)
            eligible = [r for r in rows if r['status'] == 'eligible']
            probabilities = np.array([float(r['selection_probability']) for r in eligible])
            expected_probabilities = selection_probabilities([float(r['log_weight']) for r in eligible])
            selected_rows = [r for r in rows if r['selected'] == 'True']
            chosen = selected_rows[0] if len(selected_rows) == 1 else {}
            weights_error = max(abs(float(r['log_weight'])-weight_terms(float(r['continuous_overlap_km2']),
                field.area, land.area, float(r['natural_boundary_fraction']), float(r['normalized_depth']),
                selection['design'])['log_weight']) for r in eligible)
            paths = load(p/'entry_paths.json')['paths']
            all_outside = all(not field.geometry.intersects(window_polygon(path[key], make_rotation(np.radians(path['rotation_deg']))))
                              for path in paths for key in ('start_center_source_km', 'end_center_source_km'))
            trajectories_valid = True
            for path in paths:
                group = [r for r in rows if int(r['path_id']) == path['path_id']]
                fractions = np.array([float(r['traversal_fraction']) for r in group])
                expected = np.array(path['boundary_source_km'])+(path['interval_km'][0]+
                    np.diff(path['interval_km'])[0]*fractions)[:, None]*np.array(path['inward_direction'])
                actual = np.array([[float(r['center_source_x_km']), float(r['center_source_y_km'])] for r in group])
                trajectories_valid &= (len(group) == selection['design']['positions_per_path'] and
                    np.array_equal((fractions*len(group)).astype(int), np.arange(len(group))) and
                    np.allclose(actual, expected, rtol=0, atol=1e-8))
            with np.load(p/'displacement.npz') as displacement:
                window_displacement_error = float(np.max(abs(displacement['window_m']-window.displacement(0., 48e6))))
            local.extend([
                ('coverage gates on continuous field', measured['status'] == 'eligible'),
                ('coverage gates on saved raster', gate(float(cropped['pink_overlap'].sum()), field.area, land.area, selection['design']) == 'eligible'),
                ('small exemption uses complete area before sampling', selection['small_event_exemption'] == (field.area/land.area < selection['design']['minimum_coverage'])),
                ('selected area and depth recompute', abs(measured['coverage']-selection['coverage']) < 1e-12 and abs(measured['normalized_depth']-selection['normalized_depth']) < 1e-12),
                ('candidate probability normalization', bool(np.all(probabilities > 0) and abs(probabilities.sum()-1) < 1e-12 and np.allclose(probabilities, expected_probabilities, rtol=1e-12, atol=0))),
                ('all candidate weights follow saved design', weights_error < 1e-12),
                ('rejected candidates have zero probability', all(float(r['selection_probability']) == 0 for r in rows if r['status'] != 'eligible')),
                ('one selected positive-probability candidate', len(selected_rows) == 1 and int(chosen['candidate_id']) == selection['candidate_id'] and float(chosen['selection_probability']) == selection['selection_probability'] > 0),
                ('full traversal endpoints outside', all_outside),
                ('trajectory strata and positions', bool(trajectories_valid)),
                ('saved candidate counts', len(rows) == selection['candidate_count'] and len(eligible) == selection['eligible_count']),
                ('natural zero edges evaluate to zero', field.boundary_max_rate < 1e-12),
                ('natural boundary lengths exclude crop edge', abs(measured['natural_boundary_in_window_km']-selection['natural_boundary_in_window_km']) < 1e-8),
                ('saved full-field input hashes', all(sha(p/name) == value for name, value in selection['field_input_hashes'].items())),
                ('window displacement queries original history', window_displacement_error < 1e-8),
                ('batch selection matches event record', row['selection'] == selection),
            ])
            if require_figures:
                local.append(('window diagnostics saved', all((p/name).is_file() for name in
                    ('window_diagnostics.png', 'window_diagnostics.svg', 'window_diagnostics.json'))))
        if require_figures:
            geometry = load(p/'display_geometry.json'); egeometry = load(p/'E_geometry.json')
            panels = geometry['panels'][:3]
            local.append(('A B C shared geometry', all(v['xlim'] == panels[0]['xlim'] and v['ylim'] == panels[0]['ylim']
                and np.allclose(v['axes_bbox_px'], panels[0]['axes_bbox_px'], atol=1e-6) for v in panels)))
            local.append(('E shared geometry', all(v['xlim'] == panels[0]['xlim'] and v['ylim'] == panels[0]['ylim'] for v in egeometry['panels'])))
            edges = load(output/'color_scale.json')['edges_mm_yr']
            local.append(('one shared numeric color scale', geometry['color_edges_mm_yr'] == edges == egeometry['color_edges_mm_yr']))
            local.append(('dual time axis aligned', egeometry['timeline']['geological_interval'] == [0., 48.]
                and egeometry['timeline']['activity_interval'] == [event['start_sim_Myr'], event['natural_end_sim_Myr']]))
            local.append(('all A E artifacts exist', all((p/f'{letter}.{ext}').is_file() for letter in 'ABCDE' for ext in ('png', 'svg'))))
        geometry_hashes.append(sha(p/'mesh.npz'))
        event_results.append(dict(event_id=event['event_id'], checks=[dict(check=k, passed=v) for k, v in local],
            passed=all(v for _, v in local), integration_additivity_max_m=integration_error,
            crop_query_max_m_per_yr=mapping_error, frame_float32_max_m_per_yr=frame_error))
    checks.append(dict(check='independent event parameter arrays', passed=len(set(geometry_hashes)) == len(geometry_hashes)))
    if (output/'resampling_preservation.json').exists():
        from .resampling import immutable_hashes
        preservation = load(output/'resampling_preservation.json')
        checks.append(dict(check='complete inputs and displacement preserved through resampling and rendering',
            passed=preservation['before'] == preservation['after'] == immutable_hashes(output, batch),
            file_count=preservation['unchanged_file_count'], displacement_arrays=preservation['complete_displacement_count']))
    for world in batch['worlds']:
        coarse, fine = simulate(world['seed'], .5), simulate(world['seed'], .007)
        times_a = np.array([e['start_sim_Myr'] for e in coarse['events']])
        times_b = np.array([e['start_sim_Myr'] for e in fine['events']])
        checks.append(dict(check='trigger step invariance', seed=world['seed'], passed=times_a.shape == times_b.shape and np.allclose(times_a, times_b, rtol=0, atol=1e-8)))
    if require_figures:
        for page in ('gallery.html', 'window_sampling_review.html'):
            if page != 'gallery.html' and not (output/page).exists():
                continue
            text = (output/page).read_text(encoding='utf-8')
            for link in re.findall(r'(?:href|src)="([^"]+)"', text):
                if '://' not in link:
                    file = link.split('#', 1)[0] or page
                    exists = (output/file).is_file()
                    if exists and '#' in link:
                        anchor = link.split('#', 1)[1]
                        exists = f'id="{anchor}"' in (output/file).read_text(encoding='utf-8')
                    all_links.append(dict(page=page, link=link, exists=exists))
        checks.append(dict(check='gallery links', passed=all(r['exists'] for r in all_links)))
    result = dict(passed=all(c['passed'] for c in checks) and all(e['passed'] for e in event_results),
        checks=checks, events=event_results, links=all_links, checked_events=len(event_results),
        scope='implementation and stored-product contracts; geological result acceptance remains separate')
    save(output/'audit.json', result)
    write_manifest(output, batch)
    print('Audit:', result['passed'], 'events:', len(event_results), flush=True)
    return result
