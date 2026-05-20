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

"""Utility formulas and parsers for GR(1) expressions."""

import re

from . import ltl as LTL

TOP_OPS = ['<->', '->', '&', '|']
IDENTIFIER_CHARS = 'A-Za-z0-9_'


def get_var_from_condition(cond):
    """Return the base variable from a single condition expression."""
    cond = cond.split('#')[0].strip()
    cond = strip_outer_parens(cond)

    while cond.startswith('!'):
        cond = cond[1:].strip()
        cond = strip_outer_parens(cond)

    if cond.startswith('next(') and cond.endswith(')'):
        cond = cond[5:-1].strip()
        cond = strip_outer_parens(cond)

    if '!=' in cond:
        lhs = cond.split('!=', 1)[0].strip()
    elif '=' in cond:
        lhs = cond.split('=', 1)[0].strip()
    else:
        lhs = cond

    if lhs.endswith("'"):
        lhs = lhs[:-1].strip()

    return lhs


def split_top_level(expr):
    """Split expression into top-level tokens and operators."""
    parts = []
    depth = 0
    index = 0
    start = 0

    while index < len(expr):
        if expr[index] == '(':
            depth += 1
            index += 1
            continue
        if expr[index] == ')':
            depth -= 1
            index += 1
            continue

        if depth == 0:
            for op in TOP_OPS:
                if expr.startswith(op, index):
                    parts.append(expr[start:index].strip())
                    parts.append(op)
                    index += len(op)
                    start = index
                    break
            else:
                index += 1
        else:
            index += 1

    parts.append(expr[start:].strip())
    return parts


def get_vars_from_eqn(eqn, verbose=False):
    """Return all base variables referenced by an equation."""
    conditions = extract_leaf_expressions(eqn, verbose=verbose)
    variable_names = [get_var_from_condition(cond) for cond in conditions]
    if verbose:
        print(f'    Variables: {variable_names}', flush=True)
    return variable_names


def replace_var_in_eqn(eqn, variable_name, replacement):
    """Replace a GR(1) variable token without touching longer identifiers."""
    formula, comment_separator, comment = eqn.partition('#')
    pattern = re.compile(
        rf'(?<![{IDENTIFIER_CHARS}]){re.escape(variable_name)}(?![{IDENTIFIER_CHARS}])'
    )
    replaced = pattern.sub(replacement, formula)
    if comment_separator:
        return replaced + comment_separator + comment
    return replaced


def strip_outer_parens(text):
    """Repeatedly remove fully-wrapping outer parentheses from expression text."""
    text = text.strip()
    while fully_wrapped_in_parens(text):
        text = text[1:-1].strip()
    return text


def fully_wrapped_in_parens(text):
    """Return True if text is fully enclosed by one outer parenthesis pair."""
    if not (text.startswith('(') and text.endswith(')')):
        return False

    depth = 0
    for index, char in enumerate(text):
        if char == '(':
            depth += 1
        elif char == ')':
            depth -= 1
            if depth == 0 and index != len(text) - 1:
                return False

        if depth < 0:
            return False

    return depth == 0


def extract_leaf_expressions(expr, verbose=False):
    """Extract atomic expressions from a composite logical expression."""
    expr = expr.split('#')[0].strip()

    while fully_wrapped_in_parens(expr):
        expr = expr[1:-1].strip()

    while expr.startswith('!'):
        expr = expr[1:].strip()
        while fully_wrapped_in_parens(expr):
            expr = expr[1:-1].strip()

    tokens = split_top_level(expr)
    if len(tokens) == 1:
        return [tokens[0]]

    leaves = []
    for token in tokens:
        if token in TOP_OPS:
            continue
        leaves.extend(extract_leaf_expressions(token, verbose=verbose))

    if verbose:
        print(f"Expression '{expr}' --> {leaves}", flush=True)
    return leaves


class GR1Formula:
    """Hold a GR(1) sub-formula and its proposition sets."""

    def __init__(self, formula_type, env_props=None, sys_props=None):
        self.sys_props = set(sys_props) if sys_props is not None else set()
        self.env_props = set(env_props) if env_props is not None else set()
        self.formulas = []
        self.type = formula_type

    def __str__(self):
        string = f"GR1Formula '{self.type}':\n"
        string += f' ENV props: {self.env_props}\n'
        string += f' SYS props: {self.sys_props}\n'
        string += 30 * '_' + '\n'
        for formula in self.formulas:
            string += f'"{formula}"\n'
        string += 30 * '_' + '\n'
        return string

    def add(self, formula):
        """Add a formula string/list or merge another GR1Formula of same type."""
        if isinstance(formula, GR1Formula):
            if self.type != formula.type:
                raise TypeError(
                    f"Cannot add formula of different type '{self.type}' vs. '{formula.type}'"
                )
            self.formulas.extend(formula.formulas)
            self.sys_props.update(formula.sys_props)
            self.env_props.update(formula.env_props)
            return

        if isinstance(formula, list):
            self.formulas.extend(formula)
        elif isinstance(formula, str):
            self.formulas.append(formula)
        else:
            raise TypeError(
                f"Cannot add formula data of type '{type(formula)}' to '{self.type}' formula"
            )

    @staticmethod
    def gen_mutex_formulas(mutex_props, verbose=False):
        """Create formulas that enforce mutual exclusion for propositions."""
        mutex_props = sorted(mutex_props)
        if verbose:
            print(f'Create mutually exclusive formula {mutex_props}', flush=True)

        mutex_formulas = [LTL.disj(mutex_props)]
        for index, prop in enumerate(mutex_props):
            for other_index in range(index + 1, len(mutex_props)):
                mutex_formulas.append(
                    LTL.neg(LTL.conj([prop, mutex_props[other_index]]))
                )

        return mutex_formulas

    @staticmethod
    def gen_precondition_formula(action, preconditions):
        """Return a precondition formula that gates an action proposition."""
        neg_preconditions = map(LTL.neg, sorted(preconditions))
        left_hand_side = LTL.disj(neg_preconditions)
        right_hand_side = LTL.neg(action)
        return LTL.implication(left_hand_side, right_hand_side)

    @staticmethod
    def gen_success_condition(success_props, success='finished'):
        """Create formula that sets success true when all success props are true."""
        return LTL.iff(success, LTL.conj(sorted(success_props)))


def main(argv=None):  # pragma: no cover
    """Run a basic demo for leaf and variable extraction."""
    _ = argv
    tests = [
        'a & b',
        'a | b',
        "!(a) & b  # note: '!' is not a top-level operator in our splitter",
        'a -> b',
        'a <-> b',
        '(a & b) -> c',
        'a -> (b | c)',
        '(a <-> (b | c)) & d',
        "gr' -> bu'",
        "(gr & complete') -> br'  # classic coffee style",
        '(a & b) -> (c | d) & e',
        'a & b  # ignore me',
        '(a & (b -> c))  # nested implication',
    ]

    print('\n=== Demo: extract_leaf_expressions / get_vars_from_eqn ===\n')
    for eqn in tests:
        print(f'EQN: {eqn}')
        leaves = extract_leaf_expressions(eqn)
        print(f'  Leaves: {leaves}')
        variable_names = get_vars_from_eqn(eqn)
        print(f'  Vars:   {variable_names}')
        print()

    try:
        formula = GR1Formula(
            formula_type='sys_trans',
            env_props={'bu', 'complete', 'fail'},
            sys_props={'gr', 'br'},
        )
        formula.add("(gr & complete') -> br'")
        formula.add(["gr' -> bu'", '!(gr & br)'])
        print('=== Demo: GR1Formula container ===')
        print(formula)
    except Exception as exc:
        print(f'(GR1Formula demo skipped due to error: {exc})')

    return 0


if __name__ == '__main__':  # pragma: no cover
    raise SystemExit(main())
