# Copyright (c) 2012, 2013 by California Institute of Technology
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

""" 
Interface to the JTLV implementation of GR(1) synthesis

JTLV: http://jtlv.ysaar.net/


based on code from:
    grgameint.py, jtlvint.py, rhtlp.py by Nok Wongpiromsarn 


@author: Vasu Raman
"""

import copy, itertools, os, re, subprocess, tempfile, textwrap
import warnings
from collections import OrderedDict

import transys
from spec import GRSpec

#for checking form of spec
import pyparsing
from pyparsing import *
from tulip import ltl_parse
from tulip.ltl_parse import *

JTLV_PATH = os.path.abspath(os.path.dirname(__file__))
JTLV_EXE = 'jtlv_grgame.jar'


def check_realizable(spec, heap_size='-Xmx128m', priority_kind=-1, init_option=1, verbose=0):
    #for standalone use
    
    """Decide realizability of specification defined by given GRSpec object.

    Return True if realizable, False if not, or an error occurs.
    """
    
    fSMV, fLTL, fAUT = createFiles(spec)
    return solve_game(spec, fSMV, fLTL, fAUT, heap_size, priority_kind, init_option, verbose)
    os.unlink(fSMV)
    os.unlink(fLTL)
    os.unlink(fAUT)
    

def solve_game(spec, fSMV, fLTL, fAUT, heap_size='-Xmx128m', priority_kind=3, init_option=1, verbose=0):
    """Decide realizability of specification defined by given GRSpec object.

    Return True if realizable, False if not, or an error occurs.
    Automaton is extracted for file names by fAUT, unless priority_kind == -1
    

    @param spec: a GRSpec object.
    @param fSMV, fLTL, fAUT: file name for use with JTLV.  This
        enables synthesize() to access them later on.
    @param heap_size: a string that specifies java heap size.

    @param priority_kind: a string of length 3 or an integer that specifies
        the type of priority used in extracting the
        automaton. Possible values of C{priority_kind} are:

            - -1 - No Automaton
            - 3 - 'ZYX'
            - 7 - 'ZXY'
            - 11 - 'YZX'
            - 15 - 'YXZ'
            - 19 - 'XZY'
            - 23 - 'XYZ'

        Here X means that the controller tries to disqualify one of
        the environment assumptions, Y means that the controller tries
        to advance with a finite path to somewhere, and Z means that
        the controller tries to satisfy one of his guarantees.

    @param init_option: an integer in that specifies how to handle the
        initial state of the system. Possible values of C{init_option}
        are

            - 0 - The system has to be able to handle all the possible initial system
              states specified on the guarantee side of the specification.
            - 1 (default) - The system can choose its initial state, in response to the initial
              environment state. For each initial environment state, the resulting
              automaton contains exactly one initial system state, starting from which
              the system can satisfy the specification.
            - 2 - The system can choose its initial state, in response to the initial
              environment state. For each initial environment state, the resulting
              automaton contain all the possible initial system states, starting from which
              the system can satisfy the specification.

    @param verbose: an integer that specifies the level of verbosity.
    """

 
    priority_kind = getPriority(priority_kind)
    
    # init_option
    if (isinstance(init_option, int)):
        if (init_option < 0 or init_option > 2):
            warnings.warn("Unknown init_option. Setting it to the default (1)")
            init_option = 1
    else:
        warnings.warn("Unknown init_option. Setting it to the default (1)")
        init_option = 1

    
    callJTLV(heap_size, fSMV, fLTL, fAUT, priority_kind, init_option, verbose)
    
    realizable = False
    
    f = open(fAUT, 'r')
    for line in f:
        if ("Specification is realizable" in line):
            realizable = True
            break
        elif ("Specification is unrealizable" in line):
            realizable = False
            break
        
    if (realizable and priority_kind > 0):
        print("\nAutomaton successfully synthesized.\n")
    elif (priority_kind > 0):
        print("\nERROR: Specification was unrealizable.\n")

    return realizable



def synthesize(spec, heap_size='-Xmx128m', priority_kind = 3, init_option = 1, verbose=0):
    """Synthesize a strategy satisfying the spec.

    Arguments are described in documentation for L{solve_game}.
    
    Return strategy as instance of Automaton class, or None if
    unrealizable or error occurs.
    """
    fSMV, fLTL, fAUT = createFiles(spec)
    
    realizable = solve_game(spec, fSMV, fLTL, fAUT, heap_size, priority_kind, init_option, verbose)
    
    
    # Build Automaton
    
    if (not realizable):
            counter_examples = getCounterExamples(fAUT, verbose=verbose)
            os.unlink(fSMV)
            os.unlink(fLTL)
            os.unlink(fAUT)
            return counter_examples
    else: 
            aut = loadFile(fAUT, spec, verbose=verbose)
            os.unlink(fSMV)
            os.unlink(fLTL)
            os.unlink(fAUT)
            return aut
        
        
def createFiles(spec):
    #Creates temporary files for read/write by JTLV
    fSMV = tempfile.NamedTemporaryFile(delete=False,suffix="smv")
    fSMV.write(generateJTLV_SMV(spec))
    fSMV.close()
    
    fLTL = tempfile.NamedTemporaryFile(delete=False,suffix="ltl")
    fLTL.write(generateJTLV_LTL(spec))
    fLTL.close()
    
    
    fAUT = tempfile.NamedTemporaryFile(delete=False)
    fAUT.close()
    return fSMV.name, fLTL.name, fAUT.name

def getPriority(priority_kind):
# Convert the priority_kind to the corresponding integer
    if (isinstance(priority_kind, str)):
        if (priority_kind == 'ZYX'):
            priority_kind = 3
        elif (priority_kind == 'ZXY'):
            priority_kind = 7
        elif (priority_kind == 'YZX'):
            priority_kind = 11
        elif (priority_kind == 'YXZ'):
            priority_kind = 15
        elif (priority_kind == 'XZY'):
            priority_kind = 19
        elif (priority_kind == 'XYZ'):
            priority_kind = 23
        else:
            warnings.warn("Unknown priority_kind. Setting it to the default (ZYX)")
            priority_kind = 3
    elif (isinstance(priority_kind, int)):
        if (priority_kind > 0 and priority_kind != 3 and priority_kind != 7 and \
                priority_kind != 11 and priority_kind != 15 and priority_kind != 19 and \
                priority_kind != 23):
            warnings.warn("Unknown priority_kind. Setting it to the default (ZYX)")
            priority_kind = 3
    else:
        warnings.warn("Unknown priority_kind. Setting it to the default (ZYX)")
        priority_kind = 3
    return priority_kind

def callJTLV(heap_size, fSMV, fLTL, fAUT, priority_kind, init_option, verbose):
    #subprocess calls to JTLV
    if (verbose > 0):
        print 'Calling jtlv with the following arguments:'
        print '  heap size: ' + heap_size
        print '  jtlv path: ' + JTLV_PATH
        print '  priority_kind: ' + str(priority_kind) + '\n'

    if (len(JTLV_EXE) > 0):
            jtlv_grgame = os.path.join(JTLV_PATH, JTLV_EXE)
            if (verbose > 1):
                print "  java", heap_size, "-jar", jtlv_grgame, fSMV, fLTL, \
                    fAUT, str(priority_kind), str(init_option)
            cmd = subprocess.call( \
                ["java", heap_size, "-jar", jtlv_grgame, fSMV, fLTL, fAUT, \
                     str(priority_kind), str(init_option)])
    else: # For debugging purpose
            classpath = os.path.join(JTLV_PATH, "JTLV") + ":" + \
                os.path.join(JTLV_PATH, "JTLV", "jtlv-prompt1.4.1.jar")
            if (verbose > 1):
                print "  java", heap_size, "-cp", classpath, "GRMain", fSMV, \
                    fLTL, fAUT, str(priority_kind), str(init_option)
            cmd = subprocess.call( \
                ["java", heap_size, "-cp", classpath, "GRMain", fSMV, fLTL, \
                     fAUT, str(priority_kind), str(init_option)])
    #         cmd = subprocess.Popen( \
    #             ["java", heap_size, "-cp", classpath, "GRMain", smv_file, ltl_file, \
    #                  aut_file, str(priority_kind), str(init_option)], \
    #                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT, close_fds=True)


def generateJTLV_SMV(spec, verbose=0):
    """Return the SMV module definitions needed by JTLV.

    It takes as input a GRSpec object.  N.B., assumes all variables
    are Boolean (i.e., atomic propositions).
    """
    smv = ""

    # Write the header
    smv+=textwrap.dedent("""

    MODULE main
        VAR
            e : env();
            s : sys();
    """);

    # Define env vars
    smv+=(textwrap.dedent("""
    MODULE env -- inputs
        VAR
    """))
    for var in spec.env_vars.keys():
        smv+= '\t\t'
        smv+= var
        smv+= ' : boolean;\n'

    
    # Define sys vars
    smv+=(textwrap.dedent("""
    MODULE sys -- outputs
        VAR
    """))
    for var in spec.sys_vars.keys():
        smv+= '\t\t'
        smv+= var
        smv+= ' : boolean;\n'
        
    return smv

def generateJTLV_LTL(spec, verbose=0):
    """Return the LTLSPEC for JTLV.

    It takes as input a GRSpec object.  N.B., assumes all variables
    are Boolean (i.e., atomic propositions).
    """
    specLTL = spec.to_jtlv()
    assumption = specLTL[0]
    guarantee = specLTL[1]
    
    if not check_gr1(assumption, guarantee, spec.env_vars.keys(), spec.sys_vars.keys()):
        raise Exception('Spec not in GR(1) format')
    
    assumption = re.sub(r'\b'+'True'+r'\b', 'TRUE', assumption)
    guarantee = re.sub(r'\b'+'True'+r'\b', 'TRUE', guarantee)
    assumption = re.sub(r'\b'+'False'+r'\b', 'FALSE', assumption)
    guarantee = re.sub(r'\b'+'False'+r'\b', 'FALSE', guarantee)

    assumption = assumption.replace('==', '=')
    guarantee = guarantee.replace('==', '=')
    
    assumption = assumption.replace('&&', '&')
    guarantee = guarantee.replace('&&', '&')
    
    assumption = assumption.replace('||', '|')
    guarantee = guarantee.replace('||', '|')
    
    # Replace any environment variable var in spec with e.var and replace any 
    # system variable var with s.var
    for var in spec.env_vars.keys():
        assumption = re.sub(r'\b'+var+r'\b', 'e.'+var, assumption)
        guarantee = re.sub(r'\b'+var+r'\b', 'e.'+var, guarantee)
    for var in spec.sys_vars.keys():
        assumption = re.sub(r'\b'+var+r'\b', 's.'+var, assumption)
        guarantee = re.sub(r'\b'+var+r'\b', 's.'+var, guarantee)

    # Assumption
    ltl = 'LTLSPEC\n(\n'
    if assumption:
        ltl += assumption
    else:
        ltl += "TRUE"
    ltl += '\n);\n'

    # Guarantee
    ltl += '\nLTLSPEC\n(\n'
    if guarantee:
        ltl += guarantee
    else:
        ltl += "TRUE"
    ltl += '\n);'    

    return ltl

def loadFile(aut_file, spec, verbose=0):
        """Construct a Mealy Machine from an aut_file.

        N.B., assumes all variables are Boolean (i.e., atomic
        propositions).

        Input:

        - `aut_file`: the name of the text file containing the
          automaton, or an (open) file-like object.

        - `spec`: a GROne spec.
        """
        env_vars = spec.env_vars.keys()  # Enforce Boolean var assumption
        sys_vars = spec.sys_vars.keys()
        
        if isinstance(aut_file, str):
            f = open(aut_file, 'r')
            closable = True
        else:
            f = aut_file  # Else, assume aut_file behaves as file object.
            closable = False
        
        #build Mealy Machine
        m = transys.MealyMachine()
    
        # input defs       
        inputs = OrderedDict([list(a) for a in \
                              zip(env_vars, itertools.repeat({0, 1}))])
        m.add_inputs(inputs)
        
        # outputs def
        outputs = OrderedDict([list(a) for a in \
                               zip(sys_vars, itertools.repeat({0, 1}))])
        m.add_outputs(outputs)
        
        # state variables def
        state_vars = outputs
        m.add_state_vars(state_vars)
        
        varnames = sys_vars+env_vars
        
        stateDict = {}               
        for line in f:
            # parse states
            if (line.find('State ') >= 0):
                stateID = re.search('State (\d+)', line)
                stateID = int(stateID.group(1))
                
            
                state = dict(re.findall('(\w+):(\w+)', line))
                for var, val in state.iteritems():
                    try:
                        state[var] = int(val)
                    except:
                        state[var] = val
                    if (len(varnames) > 0):
                        if not var in varnames:
                            print 'Unknown variable ' + var
                    
                    
                for var in varnames:
                    if not var in state.keys():
                        print 'Variable ' + var + ' not assigned'
         
            # parse transitions
            if (line.find('successors') >= 0):
                transition = re.findall(' (\d+)', line)
                for i in xrange(0,len(transition)):
                    transition[i] = int(transition[i])
            
                m.states.add(stateID)
                stateDict[stateID] = (state,transition)
                    
        # add transitions with guards to the Mealy Machine
        for from_state in stateDict.keys():
            state, transitions = stateDict[from_state]
            
            for to_state in transitions:
                guard = stateDict[to_state][0]
                try:
                    m.transitions.add_labeled(
                        from_state, to_state, guard, check=True
                    ) 
                except Exception, e:
                    raise Exception('Failed to add transition:\n' +str(e) )
        """
        # label states
        for to_state in m.states:
            predecessors = m.states.pre_single(to_state)
            
            # any incoming edges ?
            if predecessors:
                # pick a predecessor
                from_state = predecessors[0]
                trans = m.transitions.find([from_state], [to_state] )
                (from_, to_, trans_label) = trans[0]
                
                state_label = {k:trans_label[k] for k in m.state_vars}
                m.states.label(to_state, state_label)
        """
        return m
            
def getCounterExamples(aut_file, verbose=0):
    """Return a list of dictionaries, each representing a counter example.

    Input:

    - `aut_file`: a string containing the name of the file containing the
      counter examples generated by JTLV.
    """
    counter_examples = []
    line_found = False
    f = open(aut_file, 'r')
    for line in f:
        if (line.find('The env player can win from states') >= 0):
            line_found = True
            continue
        if (line_found and (len(line) == 0 or line.isspace())):
            line_found = False
        if (line_found):
            counter_ex = dict(re.findall('(\w+):([-+]?\d+)', line))
            for var, val in counter_ex.iteritems():
                counter_ex[var] = int(val)
            counter_examples.append(counter_ex)
            if (verbose > 0):
                print counter_ex
    return counter_examples


def removeComments(spec):
    #Remove comment lines from string
    speclines = spec.split('\n')
    newspec = ''
    for line in speclines:
        if not '--' in line:
            newspec+=line+'\n'
    return newspec
        



def check_gr1(assumption, guarantee, env_vars, sys_vars):
	"""
	Checks that an input (assumption spec, guarantee spec, and variables)
	form a valid GR(1) specification.
	"""

        assumption = removeComments(assumption)
        guarantee = removeComments(guarantee)
        
	# Check that dictionaries are in the correct format
	if not check_vars(env_vars):
		return False
	if not check_vars(sys_vars):
		return False

	# Check for parentheses mismatch
	if not check_parentheses(assumption):
		return False
	if not check_parentheses(guarantee):
		return False

	
	# Check that all non-special-characters metioned are variable names
	# or possible values
        varnames = env_vars+sys_vars
	if not check_spec(assumption,varnames):
		return False
	if not check_spec(guarantee, varnames):
		return False

	# Check that the syntax is GR(1). This uses pyparsing
	prop = ltl_parse.proposition
	UnaryTemporalOps = ~bool_keyword + oneOf("next") + ~Word(nums + "_")
	next_ltl_expr = operatorPrecedence(prop,
        [("'", 1, opAssoc.LEFT, ASTUnTempOp),
        ("!", 1, opAssoc.RIGHT, ASTNot),
        (UnaryTemporalOps, 1, opAssoc.RIGHT, ASTUnTempOp),
        (oneOf("& &&"), 2, opAssoc.LEFT, ASTAnd),
        (oneOf("| ||"), 2, opAssoc.LEFT, ASTOr),
        (oneOf("xor ^"), 2, opAssoc.LEFT, ASTXor),
        ("->", 2, opAssoc.RIGHT, ASTImp),
        ("<->", 2, opAssoc.RIGHT, ASTBiImp),
        (oneOf("= !="), 2, opAssoc.RIGHT, ASTComparator),
        ])
	always_expr = pyparsing.Literal("[]") + next_ltl_expr
	always_eventually_expr = pyparsing.Literal("[]") + \
	  pyparsing.Literal("<>") + next_ltl_expr
	gr1_expr = next_ltl_expr | always_expr | always_eventually_expr

	# Final Check
	GR1_expression = pyparsing.operatorPrecedence(gr1_expr, 
	 [("&", 2, pyparsing.opAssoc.RIGHT)])
        
	try: 
		GR1_expression.parseString(assumption)
	except ParseException:
		print "Assumption is not in GR(1) format."
		return False
        
	try:
		GR1_expression.parseString(guarantee)
	except ParseException:
		print "Guarantee is not in GR(1) format"
		return False
	return True



def check_parentheses(spec):
	"""Checks whether all the parentheses in a spec are closed.
	   Returns False if there are errors and True when there are no
	   errors."""

	open_parens = 0

	for index, char in enumerate(spec):
		if char == "(":
			open_parens += 1
		elif char == ")":
			open_parens -= 1

	if open_parens != 0:
		if open_parens > 0:
			print "The spec is missing " + str(open_parens) + " close-" + \
			  "parentheses or has " + str(open_parens) + " too many " + \
			  "open-parentheses"
		elif open_parens < 0:
			print "The spec is missing " + str(-open_parens) + " open-" + \
			  "parentheses or has " + str(open_parens) + " too many " + \
			  "close-parentheses"
		return False

	return True


def check_vars(varNames):
	"""Complains if any variable name is not a string, or if any is a number."""

	for item in varNames:
		# Check that the vars are strings
		if type(item) != str:
			print "Prop " + str(item) + " is invalid"
			return False

		# Check that the keys are not numbers
		try:
			int(item)
                        float(item)
			print "Prop " + str(item) + " is invalid"
			return False
		except ValueError:
			continue
	return True


def check_spec(spec, varNames):
	"""Make sure that all non operators in "spec" are in the list of vars."""
        
	# Replace all special characters with whitespace
	special_characters = ["next(", "[]", "<>", "->", "&", "|", "!",  \
	  "(", ")", "\n", "<", ">", "<=", ">=", "<->", "\t", "="]
	for word in special_characters:
		spec = spec.replace(word, "")
        
	# Now, replace all variable names and values with whitespace as well.
	for value in varNames:
		if isinstance(value, (list, tuple)):
			for individual_value in value:
				spec = spec.replace(str(individual_value), "")
		else:
			spec = spec.replace(value, "")
        
        

	# Remove all instances of "true" and "false"
	spec = spec.lower()
        
	spec.replace("true", "")
	spec.replace("false", "")
        

	# Make sure that the resulting string is empty
	spec = spec.split()
        
	return not spec


