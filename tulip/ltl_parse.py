#!/usr/bin/env python
#
# Copyright (c) 2011, 2012 by California Institute of Technology
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
#
# 1. Redistributions of source code must retain the above copyright
#    notice, this list of conditions and the following disclaimer.
# 
# 2. Redistributions in binary form must reproduce the above copyright
#    notice, this list of conditions and the following disclaimer in the
#    documentation and/or other materials provided with the distribution.
# 
# 3. Neither the name of the California Institute of Technology nor
#    the names of its contributors may be used to endorse or promote
#    products derived from this software without specific prior
#    written permission.
# 
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
# FOR A PARTICULAR PURPOSE ARE DISCLAIMED.  IN NO EVENT SHALL CALTECH
# OR THE CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
# SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
# LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF
# USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
# ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT
# OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF
# SUCH DAMAGE.
# 
# $Id:$
# LTL parser supporting JTLV, SPIN and SMV syntax (and mixtures thereof!)
# Syntax taken roughly from http://spot.lip6.fr/wiki/LtlSyntax
from pyparsing import *
import sys

# Packrat parsing - it's much faster
ParserElement.enablePackrat()

TEMPORAL_OP_MAP = \
        { "G" : "GLOBALLY", "F" : "FINALLY", "X" : "NEXT",
        "[]" : "GLOBALLY", "<>" : "FINALLY", "next" : "NEXT",
        "U" : "UNTIL", "V" : "RELEASE", "R" : "RELEASE" }

JTLV_MAP = { "GLOBALLY" : "[]", "FINALLY" : "<>", "NEXT" : "next",
        "UNTIL" : "U" }

SMV_MAP = { "GLOBALLY" : "G", "FINALLY" : "F", "NEXT" : "X",
        "UNTIL" : "U", "RELEASE" : "V" }

class LTLException(Exception):
    pass

class ASTNode(object):
    def __init__(self, s, l, t):
        # t can be a list or a list of lists, handle both
        try:
            tok = sum(t.asList(), [])
        except:
            try:
                tok = t.asList()
            except:
                # not a ParseResult
                tok = t
        self.init(tok)
    def flatten_JTLV(self, node): return node.toJTLV()
    def flatten_SMV(self, node): return node.toSMV()
    def toJTLV(self): return self.flatten(self.flatten_JTLV)
    def toSMV(self): return self.flatten(self.flatten_SMV)

class ASTVar(ASTNode):
    def __init__(self, s, l, t):
        self.val = t[0]
    def __repr__(self):
        return self.val
    def flatten(self, flattener=None, op=None):
        # just return variable name (quoted?)
        return self.val
        
class ASTBool(ASTNode):
    def __init__(self, s, l, t):
        if t[0].upper() == "TRUE":
            self.val = True
        else:
            self.val = False
    def __repr__(self):
        if self.val: return "TRUE"
        else: return "FALSE"
    def flatten(self, flattener=None, op=None):
        return str(self)

class ASTUnary(ASTNode):
    @classmethod
    def new(cls, op_node, operator=None):
        return cls(None, None, [operator, op_node])
    def init(self, tok):
        self.operand = tok[1]
        if isinstance(self, ASTUnTempOp):
            self.operator = TEMPORAL_OP_MAP[tok[0]]
    def __repr__(self):
        return ' '.join(['(', self.op(), str(self.operand), ')'])
    def flatten(self, flattener=str, op=None):
        if not op: op = self.op()
        try:
            o = flattener(self.operand)
        except AttributeError:
            o = str(self.operand)
        return ' '.join(['(', op, o, ')'])

class ASTNot(ASTUnary):
    def op(self): return "!"
class ASTUnTempOp(ASTUnary):
    def op(self): return self.operator
    def toJTLV(self):
        try:
            return self.flatten(self.flatten_JTLV, JTLV_MAP[self.op()])
        except KeyError:
            raise LTLException("Operator " + self.op() + " not supported in JTLV")
    def toSMV(self):
        return self.flatten(self.flatten_SMV, SMV_MAP[self.op()])

class ASTBinary(ASTNode):
    @classmethod
    def new(cls, (op_l, op_r), operator=None):
        return cls(None, None, [op_l, operator, op_r])
    def init(self, tok):
        # handle left-associative chains e.g. x && y && z
        if len(tok) > 3:
            tok[0] = self.__class__(None, None, tok[:-2])
            tok = [tok[0], tok[-2], tok[-1]]
        self.op_l = tok[0]
        self.op_r = tok[2]
        # generalise temporal operator
        if isinstance(self, ASTBiTempOp):
            self.operator = TEMPORAL_OP_MAP[tok[1]]
        elif isinstance(self, ASTComparator) or isinstance(self, ASTArithmetic):
            self.operator = tok[1]
    def __repr__(self):
        return ' '.join (['(', str(self.op_l), self.op(), str(self.op_r), ')'])
    def flatten(self, flattener=str, op=None):
        if not op: op = self.op()
        try:
            l = flattener(self.op_l)
        except AttributeError:
            l = str(self.op_l)
        try:
            r = flattener(self.op_r)
        except AttributeError:
            r = str(self.op_r)
        return ' '.join (['(', l, op, r, ')'])


class ASTAnd(ASTBinary):
    def op(self): return "&"
class ASTOr(ASTBinary):
    def op(self): return "|"
class ASTXor(ASTBinary):
    def op(self): return "xor"
class ASTImp(ASTBinary):
    def op(self): return "->"
class ASTBiImp(ASTBinary):
    def op(self): return "<->"
class ASTBiTempOp(ASTBinary):
    def op(self): return self.operator
    def toJTLV(self):
        try:
            return self.flatten(self.flatten_JTLV, JTLV_MAP[self.op()])
        except KeyError:
            raise LTLException("Operator " + self.op() + " not supported in JTLV")
    def toSMV(self):
        return self.flatten(self.flatten_SMV, SMV_MAP[self.op()])
class ASTComparator(ASTBinary):
    def op(self): return self.operator
class ASTArithmetic(ASTBinary):
    def op(self): return self.operator

# Literals cannot start with G, F or X unless quoted
restricted_alphas = filter(lambda x: x not in "GFX", alphas)
# Quirk: allow literals of the form (G|F|X)n[A-Za-z]* so we can have X0 etc.
var = (Word(restricted_alphas, alphanums + ".") + Optional("'") | \
        Regex("[A-Za-z][0-9][A-Za-z0-9.]*\'?") | QuotedString('"')).setParseAction(ASTVar)
atom = var | (CaselessKeyword("TRUE") | CaselessKeyword("FALSE")).setParseAction(ASTBool)
number = var | Word(nums)

# simple expression - no LTL operators
'''simple_expr = operatorPrecedence(atom,
        [("!", 1, opAssoc.RIGHT, ASTNot),
        (oneOf("& &&"), 2, opAssoc.LEFT, ASTAnd),
        (oneOf("| ||"), 2, opAssoc.LEFT, ASTOr),
        (oneOf("xor ^"), 2, opAssoc.LEFT, ASTXor),
        ("->", 2, opAssoc.RIGHT, ASTImp),
        ("<->", 2, opAssoc.RIGHT, ASTBiImp),
        (oneOf("< <= > >= != ="), 2, opAssoc.LEFT, ASTComparator),
        (oneOf("* /"), 2, opAssoc.LEFT, ASTArithmetic),
        (oneOf("+ -"), 2, opAssoc.LEFT, ASTArithmetic),
        ("mod", 2, opAssoc.LEFT, ASTArithmetic)
        ])'''

# arithmetic expression
arith_expr = operatorPrecedence(number,
        [(oneOf("* /"), 2, opAssoc.LEFT, ASTArithmetic),
        (oneOf("+ -"), 2, opAssoc.LEFT, ASTArithmetic),
        ("mod", 2, opAssoc.LEFT, ASTArithmetic)
        ])

# integer comparison expression
comparison_expr = (arith_expr + oneOf("< <= > >= != =") + arith_expr).setParseAction(ASTComparator)

proposition = comparison_expr | atom

# LTL expression
ltl_expr = operatorPrecedence(proposition,
        [("!", 1, opAssoc.RIGHT, ASTNot),
        (oneOf("G F X [] <> next"), 1, opAssoc.RIGHT, ASTUnTempOp),
        (oneOf("& &&"), 2, opAssoc.LEFT, ASTAnd),
        (oneOf("| ||"), 2, opAssoc.LEFT, ASTOr),
        (oneOf("xor ^"), 2, opAssoc.LEFT, ASTXor),
        ("->", 2, opAssoc.RIGHT, ASTImp),
        ("<->", 2, opAssoc.RIGHT, ASTBiImp),
        ("=", 2, opAssoc.RIGHT, ASTComparator),
        (oneOf("U V R"), 2, opAssoc.RIGHT, ASTBiTempOp),
        ])

def parse(formula):
    return ltl_expr.parseString(formula, parseAll=True)[0]

if __name__ == "__main__":
    ast = ltl_expr.parseString(sys.argv[1], parseAll=True)[0]
    print ast
    print ast.toJTLV()
    print ast.toSMV()