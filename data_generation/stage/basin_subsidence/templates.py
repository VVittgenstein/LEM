"""Reuse selected, frozen functions from the accepted convergent renderer.

AST extraction prevents importing the old modules' path globals and writers.
The only text adaptation in the dual timeline is the stage wording.
"""
import ast
from functools import lru_cache
import importlib.util
import sys
import numpy as np
from .common import SOURCES, EPOCHS

class StageWords(ast.NodeTransformer):
    def visit_Constant(self, node):
        if isinstance(node.value, str):
            node.value = node.value.replace('上升', '增强').replace('下降', '减弱')
        return node

@lru_cache(None)
def functions():
    namespace = dict(np=np, EPOCHS=EPOCHS, NUMBERS=list('①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳'),
        STAGE_COLORS={'增强': '#dd9b48', '维持': '#60a58d', '减弱': '#8e91bf'},
        GEO_COLORS=['#f8d292', '#f4dfa2', '#f6ebba', '#e0e9c2', '#cde1db', '#b9d6ee'])
    for name, wanted, assignments in [('convergent_render_windows.py', {'bar_size', 'draw_base', 'base_lines'}, {'LEVELS'}),
                                       ('convergent_render_time.py', {'draw_axes', 'stage_label'}, set())]:
        tree = ast.parse((SOURCES/name).read_text(encoding='utf-8'))
        selected = [node for node in tree.body if (isinstance(node, ast.FunctionDef) and node.name in wanted)
                    or (isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in assignments for t in node.targets))]
        module = StageWords().visit(ast.Module(body=selected, type_ignores=[]))
        ast.fix_missing_locations(module)
        exec(compile(module, str(SOURCES/name), 'exec'), namespace)
    return namespace

@lru_cache(None)
def palette():
    spec = importlib.util.spec_from_file_location('basin_frozen_palette', SOURCES/'viewer_colormaps.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.banded_colors('fem', 12)/255
