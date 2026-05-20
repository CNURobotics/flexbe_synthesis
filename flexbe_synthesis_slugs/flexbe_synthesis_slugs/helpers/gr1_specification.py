#!/usr/bin/env python

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

"""GR(1) specification container with structured slugs serialization helpers."""

import os

from flexbe_synthesis_slugs.helpers.gr1_formula import get_vars_from_eqn
import yaml


class GR1Specification:
    """Encode GR(1) formulas in structured slugs format."""

    SCHEMA_KEYS = {
        'spec_name',
        'system_name',
        'env_props',
        'sys_props',
        'env_init',
        'sys_init',
        'env_trans',
        'sys_trans',
        'env_liveness',
        'sys_liveness',
    }
    RUNTIME_KEYS = {'verbose'}

    def __init__(self, spec_name='', env_props=None, sys_props=None, verbose=False,
                 system_name=''):
        self.spec_name = spec_name
        self.system_name = system_name
        self.verbose = verbose
        self._custom_data = {}

        self.env_props = set(env_props) if env_props is not None else set()
        self.sys_props = set(sys_props) if sys_props is not None else set()

        self.__env_composite_props = None
        self.__sys_composite_props = None
        self.update_composite_props()

        self.env_init = {}
        self.env_trans = []
        self.env_liveness = []

        self.sys_init = {}
        self.sys_trans = []
        self.sys_liveness = []

    def update_composite_props(self):
        """Update derived proposition names for composite props (e.g., prop:state)."""
        self.__env_composite_props = set(self.env_props)
        for prop in self.env_props:
            if ':' in prop:
                self.__env_composite_props.add(prop.split(':')[0])

        self.__sys_composite_props = set(self.sys_props)
        for prop in self.sys_props:
            if ':' in prop:
                self.__sys_composite_props.add(prop.split(':')[0])

    def check_prop(self, prop):
        """Return section name for a proposition or None when unknown."""
        if prop in self.__env_composite_props:
            return 'env_props'
        if prop in self.__sys_composite_props:
            return 'sys_props'
        return None

    def summary(self):
        """Return a short per-section count summary."""
        return (
            f'    ENV: {len(self.env_props): 3d} props, clauses: {len(self.env_init): 3d} '
            f'ICs, {len(self.env_trans):3d} safety, {len(self.env_liveness): 3d} liveness\n'
            f'    SYS: {len(self.sys_props): 3d} props, clauses: {len(self.sys_init): 3d} '
            f'ICs, {len(self.sys_trans): 3d} safety, {len(self.sys_liveness): 3d} liveness'
        )

    def __str__(self):
        string = f'\n----------- {self.__class__.__name__} -----------\n'
        string += self.structured_slugs_yaml()
        string += 30 * '-' + '\n'
        string += self.summary() + '\n'
        string += 30 * '=' + '\n\n'
        return string

    def merge_gr1_specification(self, specification):
        """Merge one dictionary-style GR(1) specification into this instance."""
        if specification is None:
            print('No custom specification defined!')
            return

        for key in specification:
            key_spec = key.lower()
            if key.startswith('_GR1Specification__'):
                continue
            if key == 'INPUT':
                key_spec = 'env_props'
            elif key == 'OUTPUT':
                key_spec = 'sys_props'

            if key_spec not in self.SCHEMA_KEYS:
                self._store_custom_data(key, key_spec, specification[key])
                continue

            if not hasattr(self, key_spec):
                raise ValueError(
                    f"GR1Specification schema key '{key_spec}' is not initialized."
                )

            if key_spec in ('spec_name', 'system_name'):
                if isinstance(specification[key], str):
                    if self.verbose:
                        print(f"Loading specs for '{specification[key]}'  ...", flush=True)
                    setattr(self, key_spec, specification[key])
                else:
                    msg = (
                        f"Encountered unknown types ('{type(specification[key])}') "
                        f"for key '{key}' ('{key_spec}') when merging GR1 specs."
                    )
                    print(msg, flush=True)
                    raise ValueError(msg)
                continue

            if key_spec == 'env_props':
                self._update_env_props(specification[key])
                continue

            if key_spec == 'sys_props':
                self._update_sys_props(specification[key])
                continue

            if key_spec == 'env_init':
                self._update_env_init(specification[key])
                continue

            if key_spec == 'sys_init':
                self._update_sys_init(specification[key])
                continue

            data = getattr(self, key_spec)
            incoming = specification[key]

            if isinstance(data, list) and isinstance(incoming, list):
                if data and self.verbose:
                    print(f"Extending data list for '{key}' ('{key_spec}') ...", flush=True)
                data.extend(incoming)
            elif isinstance(data, dict) and isinstance(incoming, dict):
                if data and self.verbose:
                    print(
                        f"Updating data dictionary for '{key}' ('{key_spec}') ...",
                        flush=True,
                    )
                data.update(incoming)
            elif isinstance(data, set) and isinstance(incoming, (set, list)):
                if data and self.verbose:
                    print(f"Updating data set for '{key}' ('{key_spec}') ...", flush=True)
                data.update(incoming)
            elif data.__class__ == incoming.__class__:
                if self.verbose:
                    print(f"Overwriting data for '{key}' ('{key_spec}') ...", flush=True)
                setattr(self, key_spec, incoming)
            else:
                msg = (
                    f"Encountered unknown types ('{type(data)}', '{type(incoming)}') "
                    f"for key '{key}' ('{key_spec}') when merging GR1 specs."
                )
                print(msg, flush=True)
                raise ValueError(msg)

        self.update_composite_props()

    def _store_custom_data(self, key, key_spec, value):
        """Store unknown public spec metadata without mutating object attributes."""
        if key.startswith('_') or key_spec in self.RUNTIME_KEYS or hasattr(type(self), key_spec):
            raise ValueError(
                f"Unknown GR1 specification key '{key}' conflicts with a reserved "
                'GR1Specification name.'
            )
        if key in self._custom_data:
            if self.verbose:
                print(
                    f"\033[33mOverwriting custom GR1 specification key '{key}'.\033[0m",
                    flush=True,
                )
        elif self.verbose:
            print(
                f"\033[33mRetaining custom GR1 specification key '{key}' "
                f"('{key_spec}') as custom data. "
                'Investigate whether this key should be part of the '
                'GR1Specification schema.\033[0m',
                flush=True,
            )
        self._custom_data[key] = value

    def merge_gr1_specifications(self, specifications):
        """Merge multiple GR(1) specifications component-wise."""
        for spec in specifications:
            self.merge_gr1_specification(spec)

    def to_dict(self):
        """Return the pipeline-safe GR(1) specification payload."""
        data = {
            'spec_name': self.spec_name,
            'system_name': self.system_name,
            'env_props': set(self.env_props),
            'sys_props': set(self.sys_props),
            'env_init': dict(self.env_init),
            'sys_init': dict(self.sys_init),
            'env_trans': list(self.env_trans),
            'sys_trans': list(self.sys_trans),
            'env_liveness': list(self.env_liveness),
            'sys_liveness': list(self.sys_liveness),
        }
        for key, value in vars(self).items():
            if key in self.SCHEMA_KEYS or key in self.RUNTIME_KEYS or key.startswith('_'):
                continue
            data[key] = value
        data.update(self._custom_data)
        return data

    def merge_env_propositions(self, props):
        """Merge environment proposition names."""
        if not isinstance(props, set) or not all(isinstance(val, str) for val in props):
            raise TypeError('Environment propositions must be a set of strings.')
        self.env_props.update(props)

    def merge_sys_propositions(self, props):
        """Merge system proposition names."""
        if not isinstance(props, set) or not all(isinstance(val, str) for val in props):
            raise TypeError('System propositions must be a set of strings.')
        self.sys_props.update(props)

    def load_formulas(self, formulas):
        """Load multiple GR1Formula objects."""
        for formula in formulas:
            self.load(formula)

    def load(self, formula):
        """Load a GR1Formula into the GR(1) specification."""
        try:
            self.merge_env_propositions(formula.env_props)
            self.merge_sys_propositions(formula.sys_props)
            self.update_composite_props()

            if formula.type == 'env_init':
                self._update_env_init(formula.formulas)
            elif formula.type == 'sys_init':
                self._update_sys_init(formula.formulas)
            else:
                self._add_formula_to_list(formula.type, formula.formulas)
        except Exception as exc:
            print(exc)
            raise ValueError(
                f"The formula '{formula.__class__.__name__}' with "
                f'[{formula.__dict__.keys()}] failed to load!'
            )

    @staticmethod
    def _to_ics_dict(ics, verbose=False):
        """Convert a list of IC expressions into a proposition-keyed dictionary."""
        data = {}
        for eqn in ics:
            if len(eqn) < 1:
                if verbose:
                    print(f' Skipping IC comment : {eqn}')
                continue
            if eqn.strip()[0] == '#':
                data[(eqn,)] = eqn
                continue

            props = tuple(get_vars_from_eqn(eqn, verbose=verbose))
            if props is None or not props:
                if verbose:
                    print(f' Skipping IC comment : {eqn}')
                continue

            if props in data:
                if len(props) == 1:
                    if eqn == data[props]:
                        continue
                    if eqn.split('#')[0] == data[props]:
                        continue
                    if verbose:
                        print(f" Replacing '{props}' : '{data[props]}' with '{eqn}'")
                    data[props] = eqn
                else:
                    if verbose:
                        print(
                            f"Found duplicate set of variables for '{data[props]}' and '{eqn}'"
                        )
                    data[2 * props] = eqn
            else:
                if verbose:
                    print(f" Adding '{props}' with '{eqn}'")
                data[props] = eqn

        return data

    def _update_env_props(self, props):
        self.env_props.update(props)
        self.update_composite_props()

    def _update_sys_props(self, props):
        self.sys_props.update(props)
        self.update_composite_props()

    def _update_env_init(self, ics):
        if ics is None:
            if self.verbose:
                print('No environmental ICs', flush=True)
            return

        if isinstance(ics, list):
            if self.verbose:
                print(
                    f'ENV ICS are {type(ics)} not a dict - convert to vars:eqn dict!\n    {ics}'
                )
            ics = GR1Specification._to_ics_dict(ics, verbose=self.verbose)

        for vars_tuple, eqn in ics.items():
            if self.verbose:
                print(f'Vars[{vars_tuple}] = {eqn}')
            if vars_tuple in self.env_init:
                if eqn == self.env_init[vars_tuple]:
                    continue

                if eqn.split('#')[0].strip() == self.env_init[vars_tuple].split('#')[0].strip():
                    if '#' in eqn:
                        self.env_init[vars_tuple] += ' # ' + eqn.split('#')[1].strip()
                    continue

                if self.verbose:
                    print(
                        f"\033[33m  env_init: Update '{vars_tuple}' from "
                        f"'{self.env_init[vars_tuple]}' to '{eqn}'\033[0m",
                        flush=True,
                    )
                if len(vars_tuple) == 1:
                    self.env_init[vars_tuple] = eqn
                else:
                    self.env_init[eqn] = eqn
            else:
                for prop in vars_tuple:
                    if prop and prop.strip()[0] == '#':
                        continue
                    if prop not in self.env_props and prop not in self.__env_composite_props:
                        if self.verbose:
                            print(
                                f"\033[33m  env_init: Proposition '{prop}' not in "
                                "'env_props' - add it!\033[0m",
                                flush=True,
                            )
                        self.env_props.add(prop)
                        self.update_composite_props()
                self.env_init[vars_tuple] = eqn

    def _update_sys_init(self, ics):
        if ics is None:
            if self.verbose:
                print('No system ICs', flush=True)
            return

        if isinstance(ics, list):
            if self.verbose:
                print(
                    f'SYS ICS are {type(ics)} not a dict - convert to vars:eqn dict!\n    {ics}'
                )
            ics = GR1Specification._to_ics_dict(ics, verbose=self.verbose)

        for vars_tuple, eqn in ics.items():
            if self.verbose:
                print(f'SYS_INIT Vars[{vars_tuple}] = {eqn}')
            if vars_tuple in self.sys_init:
                if eqn == self.sys_init[vars_tuple]:
                    continue

                if eqn.split('#')[0].strip() == self.sys_init[vars_tuple].split('#')[0].strip():
                    if '#' in eqn:
                        self.sys_init[vars_tuple] += ' # ' + eqn.split('#')[1].strip()
                    continue

                if self.verbose:
                    print(
                        f"\033[33m  sys_init: Update '{vars_tuple}' from "
                        f"'{self.sys_init[vars_tuple]}' to '{eqn}'\033[0m",
                        flush=True,
                    )
                if len(vars_tuple) == 1:
                    self.sys_init[vars_tuple] = eqn
                else:
                    self.sys_init[eqn] = eqn
            else:
                for prop in vars_tuple:
                    if prop and prop.strip()[0] == '#':
                        continue
                    if prop not in self.__env_composite_props:
                        if prop not in self.sys_props and prop not in self.__sys_composite_props:
                            if self.verbose:
                                print(
                                    f"\033[33m  sys_init: Proposition '{prop}' not in "
                                    "'sys_props' - add it!\033[0m",
                                    flush=True,
                                )
                            self.sys_props.add(prop)
                            self.update_composite_props()
                self.sys_init[vars_tuple] = eqn

    def _validate_formula_props(self, formula_to_add):
        """Return list of invalid proposition names used in formula, else None."""
        props = tuple(get_vars_from_eqn(formula_to_add, verbose=self.verbose))
        if not props:
            return None

        formula = formula_to_add.split('#')[0].strip()
        if formula == '':
            return None

        props = list({prop.strip() for prop in props if prop != ''})
        is_prop = [self.check_prop(prop) is not None for prop in props]
        if all(is_prop):
            return None

        invalid_props = []
        for index, prop_ok in enumerate(is_prop):
            if not prop_ok:
                if self.verbose:
                    print(
                        f"\033[33m '{props[index]}' is not a env or sys proposition!\n"
                        f'"{formula_to_add}"\033[0m',
                        flush=True,
                    )
                invalid_props.append(props[index])

        return invalid_props

    def _add_formula_to_list(self, desired_list, formula_to_add):
        """Append or extend a target list of formulas."""
        if isinstance(formula_to_add, list):
            for thing in formula_to_add:
                self._add_formula_to_list(desired_list, thing)
            return

        if isinstance(formula_to_add, str):
            invalid = self._validate_formula_props(formula_to_add)
            if invalid:
                print(
                    f'\033[31mFormula references unknown propositions {invalid}:\n'
                    f'  {formula_to_add!r}\033[0m',
                    flush=True,
                )
                raise ValueError(
                    f'Formula references unknown propositions {invalid}: {formula_to_add!r}'
                )
            formula_lists = {
                'env_trans': self.env_trans,
                'sys_trans': self.sys_trans,
                'env_liveness': self.env_liveness,
                'sys_liveness': self.sys_liveness,
            }
            target = formula_lists.get(desired_list)
            if target is None:
                raise ValueError(f'Unknown formula list: {desired_list!r}')
            target.append(formula_to_add)
            return

        if formula_to_add is None:
            print(f'Warning: Nothing was added to {desired_list}!')
            return

        raise ValueError(
            f'Invalid input formula: {formula_to_add} Add either a string or a list of strings.'
        )

    def structured_slugs_yaml(self):
        """Return yaml serialization preserving quoted scalar style for formulas."""
        return yaml.dump(
            self,
            Dumper=GR1SpecDumper,
            width=120,
            default_flow_style=False,
            sort_keys=False,
        )

    def write_structured_slugs_file(self, folder_path):
        """Open a structuredslugs file and write all eight sections."""
        print(
            f"\nCreate structured slugs specification file for '{self.spec_name}' in "
            f"'{folder_path}'\n",
            flush=True,
        )

        filename = self.spec_name + '.structuredslugs'

        if not os.path.exists(folder_path):
            os.makedirs(folder_path)

        full_file_path = os.path.join(folder_path, filename)
        with open(full_file_path, 'w', encoding='utf-8') as spec_file:
            spec_file.write(self.structured_slugs_string())

        print(f"\nCreated specification file '{full_file_path}'\n", flush=True)

    def structured_slugs_string(self):
        """Return full .structuredslugs text for the current specification."""
        struct_slugs = ''

        struct_slugs += GR1Specification.__ordered_block_to_string(self.env_props, '[INPUT]')
        struct_slugs += GR1Specification.__ordered_block_to_string(self.sys_props, '[OUTPUT]')
        struct_slugs += '\n'

        struct_slugs += GR1Specification.__ic_dict_to_string(self.env_init, '[ENV_INIT]')
        struct_slugs += GR1Specification.__ic_dict_to_string(self.sys_init, '[SYS_INIT]')
        struct_slugs += '\n'

        struct_slugs += GR1Specification.__block_to_string(self.env_trans, '[ENV_TRANS]')
        struct_slugs += GR1Specification.__block_to_string(self.sys_trans, '[SYS_TRANS]')
        struct_slugs += '\n'

        struct_slugs += GR1Specification.__block_to_string(
            self.sys_liveness,
            '[SYS_LIVENESS]',
        )
        struct_slugs += GR1Specification.__block_to_string(
            self.env_liveness,
            '[ENV_LIVENESS]',
        )

        return struct_slugs

    @staticmethod
    def __block_to_string(block, header):
        string = f'{header}\n'
        for line in block:
            string += f'{line.strip()}\n'
        string += '\n'
        return string

    @staticmethod
    def __ordered_block_to_string(block, header):
        string = f'{header}\n'
        lines = sorted(block)
        if header == '[OUTPUT]':
            capability_decl = None
            capability_comments = []
            regular_lines = []
            for line in lines:
                stripped = line.strip()
                if stripped.startswith('capability:'):
                    capability_decl = stripped
                elif stripped.startswith('#'):
                    capability_comments.append(stripped)
                else:
                    regular_lines.append(stripped)

            if capability_decl is not None:
                string += f'{capability_decl}\n'
                for line in capability_comments:
                    string += f'{line}\n'
                for line in regular_lines:
                    string += f'{line}\n'
                string += '\n'
                return string

        for line in lines:
            string += f'{line.strip()}\n'
        string += '\n'
        return string

    @staticmethod
    def __ic_dict_to_string(block, header):
        string = f'{header}\n'
        for key in sorted(block.keys()):
            string += f'{block[key].strip()}\n'
        string += '\n'
        return string


class GR1SpecDumper(yaml.SafeDumper):
    """YAML dumper that preserves double-quoted scalars and serializes GR1Specification."""

    def represent_str(self, data):
        return self.represent_scalar('tag:yaml.org,2002:str', data, style='"')

    @staticmethod
    def represent_gr1_spec(dumper, obj):
        values = vars(obj)
        result = {}
        keys_raw = sorted(values.keys())
        keys_ordered = [
            'spec_name',
            'env_props',
            'sys_props',
            'env_init',
            'sys_init',
            'env_trans',
            'sys_trans',
            'env_liveness',
            'sys_liveness',
        ]
        keys = []
        for key in keys_ordered:
            if key in keys_raw:
                keys.append(key)
                keys_raw.remove(key)
            else:
                print(f"Key '{key}' not found in GR1Spec!")

        keys += [
            key for key in keys_raw if not key.startswith('_GR1Specification__')
        ]

        for key in keys:
            value = values[key]
            if isinstance(value, set) and key in ('env_props', 'sys_props'):
                result[key] = list(value)
            elif isinstance(value, dict) and key in ('env_init', 'sys_init'):
                result[key] = list(value.values())
            else:
                result[key] = value

        return dumper.represent_mapping('!GR1Specification', result)


GR1SpecDumper.add_representer(str, GR1SpecDumper.represent_str)
GR1SpecDumper.add_representer(GR1Specification, GR1SpecDumper.represent_gr1_spec)


def main():  # pragma: no cover
    """Manual debug entry point."""
    pass


if __name__ == '__main__':  # pragma: no cover
    gr1 = GR1Specification()
    print(gr1)
