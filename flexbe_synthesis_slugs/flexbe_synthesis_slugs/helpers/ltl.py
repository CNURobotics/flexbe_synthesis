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

"""
Boolean operators and the 'next' LTL operator.

The remaining LTL operators are not (currently) needed because
the specification module is using the .structuredslugs format.
"""


def conj(terms):
    terms_list = list(terms)
    if not terms_list:
        raise ValueError('LTL.conj requires at least one term')
    if len(terms_list) == 1:
        return terms_list[0]
    return paren(' & '.join(terms_list))


def disj(terms):
    terms_list = list(terms)
    if not terms_list:
        raise ValueError('LTL.disj requires at least one term')
    if len(terms_list) == 1:
        return terms_list[0]
    return paren(' | '.join(terms_list))


def neg(term):
    return '!' + term


def prime(term):
    return term + "'"


def _tokenize_bool_expr(expr):
    tokens = []
    i = 0
    specials = set('()&|!')
    n = len(expr)
    while i < n:
        ch = expr[i]
        if ch.isspace():
            i += 1
            continue
        if ch in specials:
            tokens.append(ch)
            i += 1
            continue
        start = i
        while i < n and expr[i] not in specials:
            i += 1
        atom = expr[start:i].strip()
        if atom:
            tokens.append(atom)
    return tokens


def _parse_bool_expr(tokens):
    idx = 0

    def parse_or():
        nonlocal idx
        node = parse_and()
        while idx < len(tokens) and tokens[idx] == '|':
            idx += 1
            node = ('or', node, parse_and())
        return node

    def parse_and():
        nonlocal idx
        node = parse_unary()
        while idx < len(tokens) and tokens[idx] == '&':
            idx += 1
            node = ('and', node, parse_unary())
        return node

    def parse_unary():
        nonlocal idx
        if idx < len(tokens) and tokens[idx] == '!':
            idx += 1
            return ('not', parse_unary())
        return parse_primary()

    def parse_primary():
        nonlocal idx
        if idx >= len(tokens):
            raise ValueError('Unexpected end of boolean expression')
        tok = tokens[idx]
        if tok == '(':
            idx += 1
            node = parse_or()
            if idx >= len(tokens) or tokens[idx] != ')':
                raise ValueError('Missing closing parenthesis in expression')
            idx += 1
            return node
        if tok in {'&', '|', ')'}:
            raise ValueError(f"Unexpected token '{tok}' in expression")
        idx += 1
        return ('atom', tok)

    tree = parse_or()
    if idx != len(tokens):
        raise ValueError(f'Unexpected trailing tokens: {tokens[idx:]}')
    return tree


def _next_atomic(term):
    if all(ch not in term for ch in '(&|)'):
        # Prefer prime notation for atomics
        return prime(term)

    if term[0] == '(' and term[-1] == ')':
        return 'next' + term
    return 'next' + paren(term)


def _is_complex_expression(term):
    # Keep conservative next(...) behavior for math/comparisons/functions.
    return any(ch in term for ch in '=<>+-*/%,')


def next(term):  # noqa: A001
    if _is_complex_expression(term):
        return _next_atomic(term)

    if '&' not in term and '|' not in term:
        return _next_atomic(term)

    tokens = _tokenize_bool_expr(term)
    tree = _parse_bool_expr(tokens)

    def flatten(node, op):
        if node[0] != op:
            return [node]
        return flatten(node[1], op) + flatten(node[2], op)

    def emit(node):
        kind = node[0]
        if kind == 'atom':
            return _next_atomic(node[1])
        if kind == 'not':
            child = node[1]
            child_expr = emit(child)
            if child[0] in {'and', 'or'}:
                return neg(paren(child_expr))
            return neg(child_expr)
        if kind == 'and':
            parts = [emit(part) for part in flatten(node, 'and')]
            return paren(' & '.join(parts))
        if kind == 'or':
            parts = [emit(part) for part in flatten(node, 'or')]
            return paren(' | '.join(parts))
        raise ValueError(f'Unhandled parse node: {kind}')

    return emit(tree)


def implication(left_hand_side, right_hand_side):
    return left_hand_side + ' -> ' + right_hand_side


def iff(left_hand_side, right_hand_side):
    return left_hand_side + ' <-> ' + right_hand_side


def paren(term):
    return '(' + term + ')'
