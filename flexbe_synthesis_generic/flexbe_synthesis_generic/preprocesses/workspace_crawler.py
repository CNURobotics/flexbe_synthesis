# Copyright 2026 Christopher Newport University
# Capable Humanitarian Robotics and Intelligent Systems Lab (CHRISLAB)
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import ast
import importlib.util
import logging
import os
import re
import time

from ament_index_python import get_packages_with_prefixes
from catkin_pkg.package import parse_package
from flexbe_synthesis_core.base_preprocess import BasePreProcess
import yaml

logger = logging.getLogger(__name__)

_BEHAVIOR_CONTAINER_NAMES = (
    'ConcurrencyContainer',
    'OperatableStateMachine',
    'PriorityContainer',
)


class WorkspaceCrawler(BasePreProcess):
    """Crawl the ROS workspace and collect available FlexBE states and behaviors."""

    def preprocess(self):
        """Discover FlexBE packages, parse python files, and write workspace map."""
        logger.info('Starting %s ...', self.name)
        start_time = time.time()
        package_files = {}
        source_files = {}
        package_parse_errors = []  # expected noise: non-FlexBE packages, missing paths, etc.
        file_parse_errors = []     # surfaced to pipeline: failures inside confirmed FlexBE pkgs

        packages_to_process = list(get_packages_with_prefixes().items())
        print(f'Found {len(packages_to_process)} packages to process ...', flush=True)
        for package_name, package_path in packages_to_process:
            package_share_path = os.path.join(package_path, 'share', package_name)
            try:
                package = parse_package(package_share_path)
                for export in package.exports:
                    if export.tagname in ('flexbe_behaviors', 'flexbe_states'):
                        spec = importlib.util.find_spec(package_name)
                        if spec and spec.origin:
                            python_lib_path = os.path.dirname(spec.origin)
                            package_files[package_name] = python_lib_path

                            package_source_files = []
                            for root, _, files in os.walk(python_lib_path):
                                for file_name in files:
                                    if (
                                        file_name.endswith('.py')
                                        and '__init__' not in file_name
                                    ):
                                        relative_path = os.path.join(root, file_name).replace(
                                            python_lib_path,
                                            '',
                                        )
                                        package_source_files.append(relative_path)
                            source_files[package_name] = package_source_files
                        else:
                            raise ValueError(

                                    f"Invalid FlexBE package '{package.name}' - "
                                    'Does not have a Python path!'

                            )
            except Exception as exc:
                package_parse_errors.append(
                    f"Failed to parse package '{package_share_path}': {exc}"
                )

        state_data_set = {}
        behavior_data_set = {}
        print(
            (
                f'Process {len(source_files)} FlexBE state and behavior '
                'packages in this workspace ...'
            ),
            flush=True,
        )
        if len(source_files) == 0:
            raise ValueError('No FlexBE states or behaviors found in this workspace!')

        for package_name, file_list in source_files.items():
            print(f"    Processing package '{package_name}' ...")
            for file_name in file_list:
                print(f"      Processing '{file_name}' ...")
                file_path = package_files[package_name] + file_name

                try:
                    title, file_type, state_data, behavior_data = (
                        self.process_python_file(file_path)
                    )
                except ValueError as exc:
                    file_parse_errors.append(str(exc))
                    continue

                if file_type == 'EventState':
                    state_data_set[title] = {
                        'data': state_data,
                        'package': package_name,
                        'file_name': file_name,
                    }
                elif file_type == 'Behavior':
                    behavior_data_set[title] = {
                        'data': behavior_data,
                        'package': package_name,
                        'file_name': file_name,
                    }
                else:
                    warning = (
                        f"      '{file_name}' was not a configured state "
                        f"or behavior located at '{package_name}'"
                    )
                    print(warning, flush=True)

        all_errors = package_parse_errors + file_parse_errors
        if all_errors:
            joined_errors = '\n'.join(f'  - {error}' for error in all_errors)
            print(
                f'\033[33mWARNING: Workspace crawl completed with {len(all_errors)} '
                f'parse error(s):\n{joined_errors}\033[0m',
                flush=True,
            )

        state_implementations = {}
        behaviors_available = {}

        print(f'    Processing {len(state_data_set)} states in data set ...', flush=True)
        for name, data in state_data_set.items():
            state_dict = {
                'name': name,
                'file_name': data['file_name'],
                'package': data['package'],
                'parameters': {},
                'outcomes': {},
                'userdata_in': {},
                'userdata_out': {},
                'description': '',
            }

            if name in state_implementations:
                print(

                        f"\033[31mWARNING: Duplicate state '{name}' is two packages!\n"
                        f"   '{data['package']}' vs. "
                        f"'{state_implementations[name]['package']}' \033[0m"

                )
                new_name = f"{state_implementations[name]['package']}/{name}"
                if new_name not in state_implementations:
                    state_implementations[new_name] = state_implementations[name]
                name = f"{data['package']}/{name}"
            state_implementations[name] = state_dict

            parsing_data = data['data'].split('\n')
            data_dict = state_dict
            try:
                for line in parsing_data:
                    stripped = line.strip()
                    if stripped.startswith('--'):
                        data_dict = self._parse_typed_docstring_line(line, '--')
                        if data_dict is not None:
                            state_dict['parameters'][data_dict['name']] = data_dict
                    elif stripped.startswith('<='):
                        output = re.split(r' {2,}|\t', line.split('<=')[1])
                        output = list(filter(lambda value: value != '', output))
                        output = [item.strip(" '\"\t\n") for item in output]
                        output = [output[0], ' '.join(output[1:])]
                        data_dict = {
                            'name': output[0],
                            'remapping': output[0],
                            'description': output[1],
                        }
                        state_dict['outcomes'][output[0]] = data_dict
                    elif stripped.startswith('>#'):
                        data_dict = self._parse_typed_docstring_line(line, '>#')
                        if data_dict is not None:
                            state_dict['userdata_in'][data_dict['name']] = data_dict
                    elif stripped.startswith('#>'):
                        data_dict = self._parse_typed_docstring_line(line, '#>')
                        if data_dict is not None:
                            state_dict['userdata_out'][data_dict['name']] = data_dict
            except Exception as exc:
                print(f"\033[31mERROR: parsing FlexBE state '{name}' !")
                print(parsing_data)
                print(30 * '=', flush=True)
                raise exc

        print(
            f'    Processing {len(behavior_data_set)} behaviors in data set ...',
            flush=True,
        )
        for name, data in behavior_data_set.items():
            print(
                f"Behavior {name:20s} - '{data['package']}{data['file_name']}'",
                flush=True,
            )
            behavior_dict = {
                'names': '',
                'file_name': data['file_name'],
                'package': data['package'],
                'statemachine': name,
                'outcomes': {},
                'userdata_in': {},
                'userdata_out': {},
                'description': '',
            }

            if name in behaviors_available:
                print(

                        '\033[31mWARNING: Duplicate behavior is two packages!\n'
                        f"   '{data['package']}' vs. "
                        f"'{behaviors_available[name]['package']}'\033[0m"

                )
                new_name = f"{behaviors_available[name]['package']}/{name}"
                if new_name not in behaviors_available:
                    behaviors_available[new_name] = behaviors_available[name]

                name = f"{data['package']}/{name}"

            behaviors_available[name] = behavior_dict

            parsing_data = data['data'].split('\n')
            data_dict = {}

            for line in parsing_data:
                line = line.strip()
                if line.startswith('$$'):
                    names = re.split(r' {2,}|\t', line.split('$$')[1])[0].strip()
                    behavior_dict['names'] = names.lower().replace(' ', '_')
                elif line.startswith('<='):
                    output = re.split(r'[ \t,]+', line.split('<=')[1])
                    output = list(filter(lambda value: value != '', output))
                    output = [item.strip(" '\"\t\n") for item in output]
                    for out in output:
                        data_dict = {'name': out, 'remapping': out}
                        behavior_dict['outcomes'][out] = data_dict
                elif line.startswith('>#'):
                    data_dict = self._parse_typed_docstring_line(line, '>#')
                    if data_dict is not None:
                        behavior_dict['userdata_in'][data_dict['name']] = data_dict
                elif line.startswith('#>'):
                    data_dict = self._parse_typed_docstring_line(line, '#>')
                    if data_dict is not None:
                        behavior_dict['userdata_out'][data_dict['name']] = data_dict
                elif line.startswith('##'):
                    data_dict = self._parse_behavior_userdata_assignment(line)
                    if data_dict is not None:
                        behavior_dict['userdata_in'][data_dict['name']] = data_dict
                        behavior_dict['userdata_out'][data_dict['name']] = dict(data_dict)

        to_yaml = {'states': state_implementations, 'behaviors': behaviors_available}

        hidden_dir = self.synthesis_home
        if not os.path.exists(hidden_dir):
            os.makedirs(hidden_dir)
            print(f'Created directory {hidden_dir}', flush=True)
        workspace_defn_fpath = os.path.join(hidden_dir, 'workspace_defn.yaml')
        print(

                '\033[38;5;208m writing composite workspace data to '
                f"{workspace_defn_fpath}'\033[0m"

        )
        with open(workspace_defn_fpath, 'w') as stream:
            yaml.dump(to_yaml, stream, default_flow_style=False)

        print(
            (
                'Created an initial workspace mapping in '
                f'{time.time() - start_time:.3f} seconds.'
            ),
            flush=True,
        )
        return [file_parse_errors]

    def _parse_typed_docstring_line(self, line, marker):
        """Parse a FlexBE docstring metadata line with optional type/description."""
        parts = re.split(r' {2,}|\t', line.split(marker, 1)[1])
        parts = [item.strip(" '\"\t\n") for item in parts if item.strip(" '\"\t\n")]
        if not parts:
            return None

        data = {
            'name': parts[0],
            'remapping': parts[0],
            'type': 'unknown',
            'description': '',
        }
        if len(parts) == 2:
            data['description'] = parts[1]
        elif len(parts) > 2:
            data['type'] = parts[1]
            data['description'] = ' '.join(parts[2:])
        return data

    def _parse_behavior_userdata_assignment(self, line):
        """Parse generated behavior userdata assignment metadata, if complete."""
        output = line.replace('##_state_machine.userdata.', '')
        output = re.split(r'\s*=\s*', output)
        output = [item.strip(" '\"\t\n") for item in output if item.strip(" '\"\t\n")]
        if len(output) < 2:
            return None

        return {
            'name': output[0],
            'remapping': output[0],
            'type': 'unknown',
            'data': str(output[1]),
        }

    def process_python_file(self, file_path):
        """Parse one Python file and extract state/behavior metadata via AST."""
        try:
            with open(file_path) as opened_file:
                source = opened_file.read()
        except OSError as exc:
            raise ValueError(f"Failed to read '{file_path}': {exc}") from exc

        try:
            tree = ast.parse(source, filename=file_path)
        except SyntaxError as exc:
            raise ValueError(f"Failed to parse Python syntax in '{file_path}': {exc}") from exc

        module_bindings = self._collect_bindings(tree.body)
        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue

            if self._has_base_class(node, 'EventState'):
                return node.name, 'EventState', ast.get_docstring(node) or '', ''

            if self._has_base_class(node, 'Behavior'):
                return (
                    node.name,
                    'Behavior',
                    '',
                    self._build_behavior_data(node, module_bindings),
                )

        return None, None, None, None

    def _build_behavior_data(self, class_node, module_bindings):
        """Build legacy behavior metadata lines from a Behavior AST node."""
        bindings = module_bindings.copy()
        behavior_lines = []
        for item in class_node.body:
            if isinstance(item, (ast.Assign, ast.AnnAssign)):
                bindings.update(self._collect_bindings([item]))

            if isinstance(item, ast.FunctionDef):
                bindings.update(self._collect_bindings(list(ast.walk(item))))
                if item.name == '__init__':
                    behavior_name = self._find_behavior_name(item, bindings)
                    if behavior_name:
                        behavior_lines.append(f'$$ {behavior_name}')
                elif item.name == 'create':
                    outcomes = self._find_container_outcomes(item, bindings)
                    if outcomes:
                        behavior_lines.append(f"<= {', '.join(outcomes)}")
                    behavior_lines.extend(self._find_userdata_assignments(item, bindings))

        docstring = ast.get_docstring(class_node)
        if docstring:
            behavior_lines.append(docstring)
        return '\n'.join(behavior_lines)

    def _find_behavior_name(self, function_node, bindings):
        """Return a literal assignment to self.name inside __init__, if present."""
        for node in ast.walk(function_node):
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue

            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if (
                    isinstance(target, ast.Attribute)
                    and target.attr == 'name'
                    and isinstance(target.value, ast.Name)
                    and target.value.id == 'self'
                ):
                    return self._resolve_string_literal(node.value, bindings)
        return None

    def _find_container_outcomes(self, function_node, bindings):
        """Return outcomes from the last state-machine container call in create()."""
        best_outcomes = []
        best_lineno = -1
        for node in ast.walk(function_node):
            call_node = None
            if isinstance(node, ast.Call):
                call_node = node
            elif isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
                call_node = node.value

            if call_node is None or not self._is_container_call(call_node):
                continue

            for keyword in call_node.keywords:
                if keyword.arg != 'outcomes':
                    continue
                outcomes = self._resolve_string_list(keyword.value, bindings)
                if outcomes is None:
                    continue
                lineno = getattr(node, 'lineno', -1)
                if lineno > best_lineno:
                    best_lineno = lineno
                    best_outcomes = outcomes
        return best_outcomes

    def _find_userdata_assignments(self, function_node, bindings):
        """Return legacy userdata assignment metadata lines from create()."""
        userdata_lines = []
        for node in ast.walk(function_node):
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue

            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                key = self._extract_userdata_key(target)
                if key is None:
                    continue

                value = self._resolve_constant(node.value, bindings)
                userdata_lines.append(f'##_state_machine.userdata.{key} = {value}')
        return userdata_lines

    def _extract_userdata_key(self, target):
        """Return `_state_machine.userdata.<key>` assignment key, if present."""
        if not isinstance(target, ast.Attribute):
            return None
        if not isinstance(target.value, ast.Attribute):
            return None
        if target.value.attr != 'userdata':
            return None
        if not isinstance(target.value.value, ast.Name):
            return None
        if target.value.value.id != '_state_machine':
            return None
        return target.attr

    def _has_base_class(self, class_node, base_name):
        """Return True if a class inherits from a base with the given name."""
        for base in class_node.bases:
            if isinstance(base, ast.Name) and base.id == base_name:
                return True
            if isinstance(base, ast.Attribute) and base.attr == base_name:
                return True
        return False

    def _is_container_call(self, call_node):
        """Return True if an AST call constructs a known FlexBE container."""
        if isinstance(call_node.func, ast.Name):
            return call_node.func.id in _BEHAVIOR_CONTAINER_NAMES
        if isinstance(call_node.func, ast.Attribute):
            return call_node.func.attr in _BEHAVIOR_CONTAINER_NAMES
        return False

    def _collect_bindings(self, nodes):
        """Collect simple name bindings from assignment statements."""
        bindings = {}
        for node in sorted(nodes, key=lambda child: getattr(child, 'lineno', -1)):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        bindings[target.id] = node.value
            elif (
                isinstance(node, ast.AnnAssign)
                and isinstance(node.target, ast.Name)
                and node.value is not None
            ):
                bindings[node.target.id] = node.value
        return bindings

    def _resolve_string_literal(self, node, bindings, seen=None):
        """Resolve a literal string or simple name indirection."""
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value

        if isinstance(node, ast.Name):
            seen = set() if seen is None else seen
            if node.id in seen or node.id not in bindings:
                return None
            seen.add(node.id)
            return self._resolve_string_literal(bindings[node.id], bindings, seen)

        return None

    def _resolve_string_list(self, node, bindings, seen=None):
        """Resolve a literal list/tuple/set of strings or simple name indirection."""
        if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            values = []
            for item in node.elts:
                resolved = self._resolve_string_literal(item, bindings, seen)
                if resolved is None:
                    return None
                values.append(resolved)
            return values

        if isinstance(node, ast.Name):
            seen = set() if seen is None else seen
            if node.id in seen or node.id not in bindings:
                return None
            seen.add(node.id)
            return self._resolve_string_list(bindings[node.id], bindings, seen)

        return None

    def _resolve_constant(self, node, bindings):
        """Resolve a scalar/list constant for legacy userdata metadata."""
        if isinstance(node, ast.Name) and node.id in bindings:
            return self._resolve_constant(bindings[node.id], bindings)

        try:
            return ast.literal_eval(node)
        except (ValueError, TypeError):
            return ''


def main(inputs):
    """Create workspace crawler preprocessor."""
    if inputs not in (None, []):
        print(
            (
                '\033[33mWARNING: WorkspaceCrawler ignores plugin inputs; '
                f'received {inputs}.\033[0m'
            ),
            flush=True,
        )
    return WorkspaceCrawler(name='WorkspaceCrawler')


def stand_alone():
    """Entry point for stand-alone execution."""
    print('Running WorkspaceCrawler in stand alone mode ...', flush=True)
    crawler = main([])
    crawler.preprocess()
    print('Done WorkspaceCrawler!')


if __name__ == '__main__':
    stand_alone()
