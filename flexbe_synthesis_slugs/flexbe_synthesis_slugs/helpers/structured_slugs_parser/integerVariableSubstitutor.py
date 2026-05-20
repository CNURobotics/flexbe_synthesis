#!/usr/bin/python
"""Apply integer-variable replacement rules to structured Slugs specifications."""

#
# Translates a structured specification into an unstructured one
# that is suitable to be read by the slugs synthesis tool

from re import match
import sys

from .Parser import Parser

# =====================================================
# Allocate global parser and parser context variables:
# - which APs there are
# - how the numbers are encoded
# =====================================================
p = Parser()
booleanAPs = []


# =====================================================
# Lexer for the LTL formulas
# =====================================================
def tokenize(text):
    """Tokenize an LTL formula into parser symbols."""
    res = []
    while text:
        # Ignoring stuff
        if text[0].isspace() or (text[0] == '\n'):
            text = text[1:]
            continue

        # Match words
        m = match("[a-zA-Z_.'@]+[a-zA-Z0-9_.'@]*", text)
        if m:
            currentSymbol = m.group(0)
            if currentSymbol in ['X', 'F', 'G', 'U', 'W', 'FALSE', 'TRUE', 'next']:
                res.append((currentSymbol,))
            else:
                currentSymbol = m.group(0)
                if currentSymbol in booleanAPs:
                    res.append(('boolID', m.group(0)))
                else:
                    res.append(('numID', m.group(0)))

            text = text[m.end(0):]
            continue

        # Match numbers
        m = match('[0-9]+', text)
        if m:
            res.append(('numeral', m.group(0)))
            text = text[m.end(0):]
            continue

        # Single-literal element
        res.append((text[0],))
        text = text[1:]
    return res


# =====================================================
# Simplify the specifications
# =====================================================
def clean_tree(tree):
    """Clean a parse tree by removing brackets and similar wrappers."""
    if tree[0] in p.terminals:
        return tree
    if tree[0] == 'Brackets':
        return clean_tree(tree[2])
    elif (tree[0] == 'Implication') and (len(tree) == 2):
        return clean_tree(tree[1])
    elif (tree[0] == 'Atomic') and (len(tree) == 2):
        return clean_tree(tree[1])
    elif (tree[0] == 'Conjunction') and (len(tree) == 2):
        return clean_tree(tree[1])
    elif (tree[0] == 'Biimplication') and (len(tree) == 2):
        return clean_tree(tree[1])
    elif (tree[0] == 'Disjunction') and (len(tree) == 2):
        return clean_tree(tree[1])
    elif (tree[0] == 'Xor') and (len(tree) == 2):
        return clean_tree(tree[1])
    elif (tree[0] == 'BinaryTemporalFormula') and (len(tree) == 2):
        return clean_tree(tree[1])
    elif (tree[0] == 'BooleanAtomicFormula') and (len(tree) == 2):
        return clean_tree(tree[1])
    elif (tree[0] == 'BooleanAtomicFormula') and (len(tree) != 2):
        raise Exception('BooleanAtomic formula must have only one successor')
    elif (tree[0] == 'UnaryFormula') and (len(tree) == 2):
        return clean_tree(tree[1])
    elif (tree[0] == 'MultiplicativeNumber') and (len(tree) == 2):
        return clean_tree(tree[1])
    elif (tree[0] == 'NumberExpression') and (len(tree) == 2):
        return clean_tree(tree[1])
    elif tree[0] == 'AtomicNumberExpression':
        if len(tree) != 2:
            raise ValueError('AtomicNumberExpression must have length 2')
        return clean_tree(tree[1])
    elif tree[0] == 'AtomicFormula':
        if len(tree) != 2:
            raise ValueError('AtomicFormula must have length 2')
        return clean_tree(tree[1])
    elif tree[0] == 'Implication':
        return [tree[0], clean_tree(tree[1]), clean_tree(tree[3])]
    elif tree[0] == 'Conjunction':
        return [tree[0], clean_tree(tree[1]), clean_tree(tree[3])]
    elif tree[0] == 'Biimplication':
        return [tree[0], clean_tree(tree[1]), clean_tree(tree[3])]
    elif tree[0] == 'Disjunction':
        return [tree[0], clean_tree(tree[1]), clean_tree(tree[3])]
    elif tree[0] == 'Xor':
        return [tree[0], clean_tree(tree[1]), clean_tree(tree[3])]
    elif tree[0] == 'BinaryTemporalFormula':
        return [tree[0], clean_tree(tree[1]), clean_tree(tree[2]), clean_tree(tree[3])]
    elif tree[0] == 'UnaryFormula':
        return [tree[0], clean_tree(tree[1]), clean_tree(tree[2])]
    elif tree[0] == 'MultiplicativeNumber':
        return [tree[0], clean_tree(tree[1]), clean_tree(tree[2]), clean_tree(tree[3])]
    elif tree[0] == 'NumberExpression':
        return [tree[0], clean_tree(tree[1]), clean_tree(tree[2]), clean_tree(tree[3])]
    elif tree[0] == 'BinaryTemporalOperator':
        # Remove the "superfluous indirection"
        return clean_tree(tree[1])
    elif tree[0] == 'UnaryTemporalOperator':
        # Remove the "superfluous indirection"
        return clean_tree(tree[1])
    elif tree[0] == 'Assignment':
        # Flatten "id" case
        A = [tree[0], tree[1][1]]
        A.extend(tree[2:])
        return A
    else:
        A = [tree[0]]
        for x in tree[1:]:
            A.append(clean_tree(x))
        return A


def flatten_as_much_as_possible(tree):
    """Flatten nested disjunctions and conjunctions."""
    # Ground case?
    if len(tree) == 1:
        return tree
    if isinstance(tree, str):
        return tree
    newTree = []
    for a in tree:
        newTree.append(flatten_as_much_as_possible(a))
    tree = newTree

    # Conjunction
    if tree[0] == 'Conjunction':
        parts = [tree[0]]
        for a in tree[1:]:
            if a[0] == 'Conjunction':
                parts.extend(a[1:])
            else:
                parts.append(a)
        return parts

    # Disjunction
    if tree[0] == 'Disjunction':
        parts = [tree[0]]
        for a in tree[1:]:
            if a[0] == 'Disjunction':
                parts.extend(a[1:])
            else:
                parts.append(a)
        return parts

    # Xor
    if tree[0] == 'Xor':
        parts = [tree[0]]
        for a in tree[1:]:
            if a[0] == 'Xor':
                parts.extend(a[1:])
            else:
                parts.append(a)
        return parts

    # Every other case
    return tree


# =====================================================
# Print Tree function
# =====================================================
def printTree(tree, depth=0):
    """Print a parse tree to stderr."""
    if isinstance(tree, str):
        print(' ' * depth + tree, file=sys.stderr)
    else:
        print(' ' * depth + tree[0], file=sys.stderr)
        for a in tree[1:]:
            printTree(a, depth + 2)


# =====================================================
# The Parsing function
# =====================================================
def parseLTL(ltlTxt, reasonForNotBeingASlugsFormula):
    """Parse structured LTL text and return a simplified syntax tree."""
    try:
        token_stream = tokenize(ltlTxt)
        tree = p.parse(token_stream)

    except p.ParseErrors as exception:
        for t, e in exception.errors:
            if t[0] == p.EOF:
                print('Formula end not expected here', file=sys.stderr)
                continue

            found = repr(t[0])
            print('Error in the property line: ' + ltlTxt, file=sys.stderr)
            print(
                '... which could not have been a slugs Polish notation line because of: '
                + reasonForNotBeingASlugsFormula,
                file=sys.stderr,
            )
            print('Could not parse %s, ' % found, file=sys.stderr)
            print(
                'Wanted a token of one of the following forms: '
                + ', '.join([repr(s) for s in e]),
                file=sys.stderr,
            )
        raise

    # Convert to a tree
    cleaned_tree = flatten_as_much_as_possible(clean_tree(tree))
    return cleaned_tree


# ============================================
# Build Slugs file - Temporal logic properties
# ============================================
def parseSimpleFormula(tree, isPrimed):
    """Translate a parsed formula tree into recursive Slugs tokens."""
    if tree[0] == 'Formula':
        assert len(tree) == 2
        return parseSimpleFormula(tree[1], isPrimed)
    if tree[0] == 'Biimplication':
        b1 = parseSimpleFormula(tree[1], isPrimed)
        b2 = parseSimpleFormula(tree[2], isPrimed)
        return ['|', '&', '!'] + b1 + ['!'] + b2 + ['&'] + b1 + b2
    if tree[0] == 'Implication':
        b1 = parseSimpleFormula(tree[1], isPrimed)
        b2 = parseSimpleFormula(tree[2], isPrimed)
        return ['|', '!'] + b1 + b2
    if tree[0] == 'Conjunction':
        ret = parseSimpleFormula(tree[1], isPrimed)
        for a in tree[2:]:
            ret = ['&'] + ret + parseSimpleFormula(a, isPrimed)
        return ret
    if tree[0] == 'Disjunction':
        ret = parseSimpleFormula(tree[1], isPrimed)
        for a in tree[2:]:
            ret = ['|'] + ret + parseSimpleFormula(a, isPrimed)
        return ret
    if tree[0] == 'UnaryFormula':
        if tree[1][0] == 'NotOperator':
            return ['!'] + parseSimpleFormula(tree[2], isPrimed)
        elif tree[1][0] == 'NextOperator':
            if isPrimed:
                raise Exception('Nested nexts are not allowed.')
            return parseSimpleFormula(tree[2], True)
    if tree[0] == 'Assignment':
        var = tree[1]
        if isPrimed:
            if "'" in var:
                raise Exception(
                    'Cannot parse input formula: variable is both primed and '
                    'in the scope of a next-operator'
                )
            var = var + "'"
        return [var]
    if tree[0] == 'TRUE':
        return ['1']
    if tree[0] == 'FALSE':
        return ['0']
    if tree[0] == 'CalculationSubformula':
        assert len(tree) == 4
        raise NotImplementedError(
            'CalculationSubformula is not supported by parseSimpleFormula.'
        )

    print('Cannot parse sub-tree!', file=sys.stderr)
    print(tree, file=sys.stderr)
    raise Exception('Slugs parsing error')


# ============================================
# Tree->Structured Slugs formula line
# ============================================
def translateTreeToStructuredSlugsLine(tree, isPrimed):
    """Render a parsed tree back to a structured Slugs formula string."""
    if tree[0] == 'Formula':
        assert len(tree) == 2
        return translateTreeToStructuredSlugsLine(tree[1], isPrimed)
    if tree[0] == 'Biimplication':
        b1 = translateTreeToStructuredSlugsLine(tree[1], isPrimed)
        b2 = translateTreeToStructuredSlugsLine(tree[2], isPrimed)
        return '((' + b1 + ') <-> (' + b2 + '))'
    if tree[0] == 'Implication':
        b1 = translateTreeToStructuredSlugsLine(tree[1], isPrimed)
        b2 = translateTreeToStructuredSlugsLine(tree[2], isPrimed)
        return '((' + b1 + ') -> (' + b2 + '))'
    if tree[0] == 'Conjunction':
        assert len(tree) > 1
        return (
            '('
            + '&'.join(
                [
                    '(' + translateTreeToStructuredSlugsLine(a, isPrimed) + ')'
                    for a in tree[1:]
                ]
            )
            + ')'
        )
    if tree[0] == 'Disjunction':
        assert len(tree) > 1
        return (
            '('
            + '|'.join(
                [
                    '(' + translateTreeToStructuredSlugsLine(a, isPrimed) + ')'
                    for a in tree[1:]
                ]
            )
            + ')'
        )
    if tree[0] == 'UnaryFormula':
        if tree[1][0] == 'NotOperator':
            return '! ' + translateTreeToStructuredSlugsLine(tree[2], isPrimed)
        elif tree[1][0] == 'NextOperator':
            if isPrimed:
                raise Exception('Nested nexts are not allowed.')
            return translateTreeToStructuredSlugsLine(tree[2], True)
    if tree[0] == 'Assignment':
        var = tree[1]
        if isPrimed:
            if "'" in var:
                raise Exception(
                    'Cannot parse input formula: variable is both primed and '
                    'in the scope of a next-operator'
                )
            var = var + "'"
        return var
    if tree[0] == 'TRUE':
        return 'TRUE'
    if tree[0] == 'FALSE':
        return 'FALSE'
    if tree[0] == 'CalculationSubformula':
        assert len(tree) == 4
        part1 = translateTreeToStructuredSlugsLine(tree[1], isPrimed)
        part2 = translateTreeToStructuredSlugsLine(tree[3], isPrimed)
        operation = tree[2][1][0]
        if operation == 'GreaterOperator':
            opString = '>'
        elif operation == 'SmallerOperator':
            opString = '<'
        elif operation == 'SmallerEqualOperator':
            opString = '<='
        elif operation == 'GreaterEqualOperator':
            opString = '>='
        elif operation == 'EqualOperator':
            opString = '='
        elif operation == 'UnequalOperator':
            opString = '!='
        else:
            print(
                'Error: Could not interpret calculation comparison operation: '
                + operation,
                file=sys.stderr,
            )
            raise 1
        return part1 + opString + part2
    print(tree, file=sys.stderr)
    if tree[0] == 'NumberExpression':
        if tree[2][0] == 'AdditionOperator':
            return (
                '(('
                + translateTreeToStructuredSlugsLine(tree[1], isPrimed)
                + ')+('
                + translateTreeToStructuredSlugsLine(tree[3], isPrimed)
                + '))'
            )
        else:
            print('Could not identify operator in NumberExpression!', file=sys.stderr)
            print(tree, file=sys.stderr)
            raise 3
    if tree[0] == 'numID':
        if isPrimed:
            print(
                'Error: This tool does not allow a next-time operator '
                'with integer variable expressions.',
                file=sys.stderr,
            )
            raise Exception('Fatal Error')
        return tree[1]
    if tree[0] == 'numeral':
        return tree[1]

    print('Cannot translate sub-tree!', file=sys.stderr)
    print(tree, file=sys.stderr)
    raise Exception('Slugs translation error')


# ============================================
# Function to check if an input line is already
# in slugs internal form. Checks that there
# will be one element on the stack left when
# applying the operations from right to left
# ============================================
def isValidRecursiveSlugsProperty(tokens):
    """Check whether a token sequence is already in recursive Slugs form."""
    tokens = [a for a in tokens if a != '']
    if '$' in tokens:
        return (True, "Found a '$' in the property.")
    stacksize = 0
    for i in range(len(tokens) - 1, -1, -1):
        currentToken = tokens[i]
        if currentToken == '|' or currentToken == '&' or currentToken == '^':
            if stacksize < 2:
                return (False, 'Rejected part due to stack underflow')
            stacksize -= 1
        elif currentToken == '!':
            pass
        elif currentToken == '1' or currentToken == '0':
            stacksize += 1
        else:
            # Check if valid input or output bit
            if currentToken[len(currentToken) - 1] == "'":
                currentToken = currentToken[0: len(currentToken) - 1]
            if currentToken in booleanAPs:
                stacksize += 1
            elif currentToken == '0' or currentToken == '1':
                stacksize += 1
            else:
                return (
                    False,
                    'Rejected part "' + tokens[i] + '" when reading right-to-left.',
                )

    return (stacksize == 1, 'Stack size at end: ' + str(stacksize))


# -------------------------------------------------------------------------------
# Recursive worker function to replace variables by other expressions.
# -------------------------------------------------------------------------------
def treeReplaceExpression(tree, replacementData):
    """Replace integer-expression leaves and collect additive replacement terms."""
    # Consider all possible subexpression types explicitly so that if more features are added that
    # are incompatible with the current script, it stops working instead of working incorrectly
    # (examples are multiplication and everything that requires proper bracing/scoping within the
    # sub-expressions left and right of the comparison operato)
    if tree[0] == 'numeral' or tree[0] == 'AdditionOperator':
        return (tree, [])
    if tree[0] == 'numID':
        if tree[1] in replacementData:
            (a, b) = replacementData[tree[1]]
            return (('numID', a), [b])
        else:
            return (tree, [])
    if (
        tree[0] == 'NumberBrackets'
        or tree[0] == 'AtomicNumberExpression'
        or tree[0] == 'NumberExpression'
    ):
        # Bracketed expressions are fine as long as there are no multiplications/subtractions.
        # In case of allowed operations, we can also just recurse
        newTree = [tree[0]]
        newReplacements = []
        for a in tree[1:]:
            (addTree, addReplacement) = treeReplaceExpression(a, replacementData)
            newTree.append(addTree)
            newReplacements.extend(addReplacement)
        return (tuple(newTree), newReplacements)
    if tree[0] == 'MultiplicationOperator' or tree[0] == 'NegationOperator':
        raise Exception(
            'Error: Multiplications and negations are not allowed in '
            'integerVariableSubstitutor'
        )
    if tree[0] == 'LeastSignificantBitOverwriteExpression':
        assert len(tree) == 2  # Must not be used when using the substitutor
        return treeReplaceExpression(tree[1], replacementData)

    print(
        'Error: Could not apply treeReplaceExpression to expression of the type '
        + str(tree[0]),
        file=sys.stderr,
    )
    printTree(tree)
    raise Exception('Failed')


def treeReplace(tree, replacementData):
    """Apply replacement expressions recursively to an LTL parse tree."""
    if tree[0] == 'CalculationSubformula':
        (newSubtree1, toBeAdded1) = treeReplaceExpression(tree[1], replacementData)
        (newSubtree2, toBeAdded2) = treeReplaceExpression(tree[3], replacementData)
        # print "TBA: "+str(toBeAdded1)
        # print "TBA: "+str(toBeAdded2)
        if len(toBeAdded2) == 0:
            translatedSubtree1 = newSubtree1
        else:
            translatedSubtree1 = (
                'NumberExpression',
                newSubtree1,
                ('AdditionOperator',),
                ('numID', '+'.join(toBeAdded2)),
            )
        if len(toBeAdded1) == 0:
            translatedSubtree2 = newSubtree2
        else:
            translatedSubtree2 = (
                'NumberExpression',
                newSubtree2,
                ('AdditionOperator',),
                ('numID', '+'.join(toBeAdded1)),
            )
        return (tree[0], translatedSubtree1, tree[2], translatedSubtree2)
    elif tree[0] == 'Assignment':
        # This is the case of a Bool value that we do not want to "rip apart"
        return tree
    else:
        return tuple([tree[0]] + [treeReplace(a, replacementData) for a in tree[1:]])


# ============================================
# Main worker
# ============================================
def performReplacement(inputFile, replacementFile):
    """Run replacements from file and print rewritten structured Slugs output."""
    # Read replacement file
    replacementDataExpressions = {}
    replacementDataDefinitions = {}
    with open(replacementFile) as fileReader:
        for line in fileReader.readlines():
            line = line.strip()
            if len(line) > 0 and line[0] != '#':
                lineParts = line.split(',')
                if len(lineParts) == 2:
                    replacementDataDefinitions[lineParts[0]] = lineParts[1]
                elif len(lineParts) == 3:
                    replacementDataExpressions[lineParts[0]] = (
                        lineParts[1],
                        lineParts[2],
                    )

    # Read specification file
    specFile = open(inputFile)
    mode = ''
    lines = {
        '[ENV_TRANS]': [],
        '[ENV_INIT]': [],
        '[INPUT]': [],
        '[OUTPUT]': [],
        '[SYS_TRANS]': [],
        '[SYS_INIT]': [],
        '[ENV_LIVENESS]': [],
        '[SYS_LIVENESS]': [],
        '[OBSERVABLE_INPUT]': [],
        '[UNOBSERVABLE_INPUT]': [],
        '[CONTROLLABLE_INPUT]': [],
    }

    for line in specFile.readlines():
        line = line.strip()
        if line == '':
            pass
        elif line.startswith('['):
            mode = line
            # if not mode in lines:
            #    lines[mode] = []
        else:
            if mode == '' and line.startswith('#'):
                # Initial comments
                pass
            else:
                lines[mode].append(line)

    specFile.close()

    # -----------------------------------------------------------
    # Begin replacement. We start with the input and output lines
    # -----------------------------------------------------------
    for variableType in [
        '[INPUT]',
        '[OUTPUT]',
        '[OBSERVABLE_INPUT]',
        '[UNOBSERVABLE_INPUT]',
        '[CONTROLLABLE_INPUT]',
    ]:
        if len(lines[variableType]) > 0:
            print(variableType)
            for line in lines[variableType]:
                line = line.strip()
                if ':' not in line:
                    booleanAPs.append(line)
                    booleanAPs.append(line + "'")
                if line.startswith('#'):
                    print(line)
                else:
                    if line in replacementDataDefinitions:
                        print(replacementDataDefinitions[line])
                    else:
                        print(line)
            print('')

    # ---------------------------------------
    # Now through the properties and translate
    # ---------------------------------------
    for propertyType in [
        '[ENV_TRANS]',
        '[ENV_INIT]',
        '[SYS_TRANS]',
        '[SYS_INIT]',
        '[ENV_LIVENESS]',
        '[SYS_LIVENESS]',
    ]:
        if len(lines[propertyType]) > 0:
            print(propertyType)

            # Test for conformance with recursive definition
            for a in lines[propertyType]:
                if a.strip()[0:1] == '#':
                    print(a)
                else:
                    (isSlugsFormula, reasonForNotBeingASlugsFormula) = (
                        isValidRecursiveSlugsProperty(a.strip().split(' '))
                    )
                    if isSlugsFormula:
                        print(a)
                    else:
                        tree = parseLTL(a, reasonForNotBeingASlugsFormula)
                        tree = treeReplace(tree, replacementDataExpressions)
                        # printTree(tree)
                        print(translateTreeToStructuredSlugsLine(tree, False))
            print('')


# ==================================
# Entry point
# ==================================
if __name__ == '__main__':
    if len(sys.argv) < 3:
        print(
            'Error: Need input file and replacement file as parameters', file=sys.stderr
        )
        sys.exit(1)

    inputFile = sys.argv[1]
    replacementFile = sys.argv[2]
    performReplacement(inputFile, replacementFile)
