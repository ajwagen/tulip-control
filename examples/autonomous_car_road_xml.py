#!/usr/bin/env python
"""
The autonomous car example presented in the CDC/HSCC paper,
illustrating the use of rhtlp module.

ORIGINALLY BY Nok Wongpiromsarn (nok@cds.caltech.edu)
August 28, 2010

Small modifications by SCL <slivingston@caltech.edu>
"""


import sys, os
import math
from numpy import array
from subprocess import call

from tulip.polytope_computations import Polytope
from tulip.discretizeM import CtsSysDyn
from tulip.spec import GRSpec
from tulip.rhtlp import RHTLPProb, ShortHorizonProb
from tulip import conxml
from tulip import congexf


##############################
# Various runtime parameters #
##############################
load_from_XML = False

# Road configuration
roadWidth = 3
roadLength = 10

# Problem setup
dpopup = 2
dsr = 3
horizon = 3


if not load_from_XML:

    # Continuous dynamics: \dot{x} = u_x, \dot{y} = u_y
    A = array([[1, 0.],[ 0., 1]])
    B = array([[1.1052, 0.],[ 0., 1.1052]])
    U = Polytope(array([[1., 0.],[-1., 0.], [0., 1.], [0., -1.]]),
                 array([[1.],[1.],[1.],[1.]]))
    sys_dyn = CtsSysDyn(A,B,[],U,[])


    # Variables and propositions
    env_vars = {}
    cont_props = {}
    for x in xrange(0, roadLength):
        for y in xrange(0, roadWidth):
            id = str((y*roadLength)+x)
            obs = 'obs' + id
            cell = 'X' + id
            env_vars[obs] = 'boolean'
            cont_props[cell] = Polytope(array([[1., 0.],[-1., 0.],
                                               [0., 1.], [0., -1.]]),
                                        array([[x+1.], [-float(x)],
                                               [y+1.], [-float(y)]]))

    # Specification
    spec = GRSpec(env_init='', sys_init='', env_safety='', sys_safety='',
                  env_prog='', sys_prog='')
    init_cells = range(0, roadLength*(roadWidth-1)+1, roadLength)

    # Assumption on the initial state
    for id in xrange(0, roadLength*roadWidth):
        if (not id in init_cells):
            if (len(spec.sys_init) > 0):
                spec.sys_init += ' & '
            spec.sys_init += '!X' + str(id)
    spec.sys_init = '(' + spec.sys_init + ')'


    # If started in the left lane, then there is an obstacle in the right lane.
    for x in xrange(0, roadLength):
        cell = ''
        for y in xrange(roadWidth/2, roadWidth):
            if (len(cell) > 0):
                cell += ' | '
            cell += 'X' + str(y*roadLength + x)
        obs = ''
        for obsx in xrange(max([0, x-1]), min([roadLength, x+2])):
            if (len(obs) > 0):
                obs += ' | '
            obs += 'obs' + str(obsx)
        if (len(spec.sys_init) > 0):
            spec.sys_init += ' &\n\t'
        spec.sys_init += '((' + cell + ') -> (' + obs + '))'

    for id in init_cells:
        obs = 'obs' + str(id)
        cell = 'X' + str(id)
        # The robot does not collide with an obstacle
        if (len(spec.sys_init) > 0):
            spec.sys_init += ' &\n\t'
        spec.sys_init += '(' + cell + ' -> !' + obs + ')'

        # The robot is not surrounded by obstacles
        spec.sys_init += ' &\n\t'
        spec.sys_init += '(' + cell + ' -> !(' + 'obs' + str(id+1) 
        if (math.floor(id/roadLength) < roadWidth - 1):
            spec.sys_init += ' & obs' + str(id + roadLength)
        if (math.floor(id/roadLength) > 0):
            spec.sys_init += ' & obs' + str(id - roadLength)
        spec.sys_init += '))'

    # Assumption on the environment
    # Obstacle is always detected before the robot gets too close to it
    for x in xrange(0,roadLength):
        cell = ''
        for j in xrange(max([0, x-dpopup]), min([roadLength, x+dpopup+1])):
            for k in xrange(0, roadWidth):
                if (len(cell) > 0):
                    cell += ' | '
                cell += 'X' + str(k*roadLength + j)
        for k in xrange(0, roadWidth):
            obs = 'obs' + str(k*roadLength+x)
            if (len(spec.env_safety) > 0):
                spec.env_safety += ' &\n\t'
            spec.env_safety += '(((' + cell +') & !' + obs + ') -> next(!' + obs + '))'

    # Sensing range
    for x in xrange(0,roadLength):
        cell = ''
        for y in xrange(0,roadWidth):
            if (len(cell) > 0):
                cell += ' | '
            cell += 'X' + str(y*roadLength + x)
        obs = ''
        for j in xrange(x+dsr, roadLength):
            for k in xrange(0, roadWidth):
                if (len(obs) > 0):
                    obs += ' & '
                obs += '!obs' + str(k*roadLength + j)
        for j in xrange(0, x-dsr+1):
            for k in xrange(0, roadWidth):
                if (len(obs) > 0):
                    obs += ' & '
                obs += '!obs' + str(k*roadLength + j)
        if (len(obs) > 0):
            if (len(spec.env_safety) > 0):
                spec.env_safety += ' &\n\t'
            spec.env_safety += '((' + cell + ') -> (' + obs + '))'

    # The road is not blocked
    for i in xrange(0, roadLength):
        for j in xrange(max([0, i-1]), min([i+2, roadLength])):
            for k in xrange(max([0,j-1]), min([j+2,roadLength])):
                if (len(spec.env_safety) > 0):
                    spec.env_safety += ' &\n\t'
                spec.env_safety += '!(obs' + str(i) + ' & obs' + str(roadLength+j) + \
                    ' & obs' + str(2*roadLength+k) + ')'

    for x in xrange(0, roadLength-2):
        if (len(spec.env_safety) > 0):
            spec.env_safety += ' &\n\t'
        spec.env_safety += '((obs' + str(roadLength+x) + ' & obs' + str(roadLength+x+1) + \
            ') -> (!obs' + str(x+2) + ' & !obs' + str(roadLength+x+2) + \
            ' & !obs' + str(2*roadLength+x+2) + '))'


    # Obstacle does not disappear
    for x in xrange(0, roadLength):
        for y in xrange(0, roadWidth):
            obs = 'obs' + str((y*roadLength)+x)
            if (len(spec.env_safety) > 0):
                spec.env_safety += ' &\n\t'
            spec.env_safety += '(' + obs + ' -> next(' + obs + '))'

    # Guarantee
    # No collision
    for x in xrange(0, roadLength):
        for y in xrange(0, roadWidth):
            id = str((y*roadLength)+x)
            obs = 'obs' + id
            cell = 'X' + id
            if (len(spec.sys_safety) > 0):
                spec.sys_safety += ' &\n\t'
            spec.sys_safety += '(' + obs + ' -> !' + cell + ')'

    # Stay in the right lane unless the lane is blocked
    for x in xrange(0, roadLength):
        cell = ''
        for y in xrange(int(math.floor(roadWidth/2)), roadWidth):
            if (len(cell) > 0):
                cell += ' | '
            cell += 'X' + str(y*roadLength + x)
        obs = ''
        for obsx in xrange(max([0, x-1]), min([roadLength, x+2])):
            for obsy in xrange(0, int(math.floor(roadWidth/2)+1)):
                if (len(obs) > 0):
                    obs += ' | '
                obs += 'obs' + str(obsy*roadLength + obsx)
        if (len(spec.sys_safety) > 0):
            spec.sys_safety += ' &\n\t'
        spec.sys_safety += '((' + cell + ') -> (' + obs + '))'

    # Get to the end of the road
    final_cells = range(roadLength-1, roadLength*roadWidth, roadLength)
    cell = ''
    for fcell in final_cells:
        if (len(cell) > 0):
            cell += ' | '
        cell += 'X' + str(fcell)
    spec.sys_prog = '(' + cell + ')'

    rhtlpprob = RHTLPProb(shprobs=[], Phi='True', discretize=False,
                          env_vars = env_vars, disc_props = {},
                          cont_props = cont_props, spec = spec,
                          sp_name = os.path.join('acar_spec', 'root'))
    disc_dynamics = rhtlpprob.getDiscretizedDynamics()

    conxml.writeXMLfile("acar_example.xml", rhtlpprob, spec,
                        sys_dyn, pretty=True)

else:  # Read from tulipcon XML file
    (rhtlpprob, sys_dyn, aut) = conxml.readXMLfile("acar_example.xml")
    disc_dynamics = rhtlpprob.getDiscretizedDynamics()
    cont_props = rhtlpprob.getContProps()


# Short Horizon Problems

for x_init in xrange(0, roadLength):
    print 'adding W' + str(x_init)
    # Environment variables
    env_vars = {}
    for y in xrange(0, roadWidth):
        for x in xrange(x_init, x_init+horizon):
            varname = 'obs' + str((y*roadLength)+x)
            env_vars[varname] = 'boolean'

    # System continuous variable
    sys_cont_vars = ['x', 'y']
    cont_state_space = Polytope(array([[1., 0.], [-1., 0.], [0., 1.], [0., -1.]]),
                                array([[float(min([x_init+horizon, roadLength]))],
                                       [float(-x_init)],
                                       [float(roadWidth)],
                                       [0.]]))

    # W
    initCells = range(x_init, x_init+roadLength*(roadWidth-1)+1, roadLength)
    W = ''
    for i in initCells:
        if (len(W) > 0):
            W += ' | '
        W += 'X' + str(i)
    print W

    # Phi
    Phi = ''
    for id in initCells:
        obs = 'obs' + str(id)
        cell = 'X' + str(id)
        # The robot does not collide with an obstacle
        if (len(Phi) > 0):
            Phi += ' &\n\t'
        Phi += '(' + cell + ' -> !' + obs + ')'

        # The robot is not surrounded by obstacles
        if (id % roadLength < roadLength-1):
            Phi += ' &\n\t'
            Phi += '(' + cell + ' -> !(' + 'obs' + str(id+1) 
            if (math.floor(id/roadLength) < roadWidth - 1):
                Phi += ' & obs' + str(id + roadLength)
            if (math.floor(id/roadLength) > 0):
                Phi += ' & obs' + str(id - roadLength)
            Phi += '))'

        # If started in the left lane, then there is an obstacle in the right lane.
        if (math.floor(id/roadLength) >= math.floor(roadWidth/2)):
            Phi += ' &\n\t'
            obs = ''
            x = id % roadLength
            for obsx in xrange(max([0, x-1]), min([roadLength, x+2])):
                for obsy in xrange(0, int(math.floor(roadWidth/2)+1)):
                    if (len(obs) > 0):
                        obs += ' | '
                    obs += 'obs' + str(obsy*roadLength + obsx)
            Phi += '(' + cell + ' -> (' + obs + '))'

    rhtlpprob.addSHProb(ShortHorizonProb(W=W, FW=[], Phi=Phi,
                                         global_prob = rhtlpprob,
                                         env_vars = env_vars,
                                         sys_disc_vars = {},
                                         disc_props = {},
                                         cont_state_space=cont_state_space,
                                         cont_props = cont_props,
                                         sys_dyn = sys_dyn,
                                         sp_name = os.path.join('acar_spec',
                                                                'W'+str(x_init))))

for x_init in xrange(0, roadLength):
    FWind = min([roadLength-1, x_init+horizon-1])
    rhtlpprob.shprobs[x_init].setFW(FW=rhtlpprob.shprobs[FWind], update=True, verbose=3)

# Validate whether rhtpprob is valid
ret = rhtlpprob.validate()
print ret

# The result of the above validate() call is
# state 
#   (= X25 false)
#   (= X24 false)
#   (= X27 false)
#   (= X26 false)
#   (= X23 false)
#   (= X22 false)
#   (= X21 false)
#   (= X20 false)
#   (= X8 false)
#   (= X9 false)
#   (= X2 false)
#   (= X3 false)
#   (= X0 false)
#   (= X1 false)
#   (= X6 false)
#   (= X7 false)
#   (= X4 false)
#   (= X5 false)
#   (= X18 false)
#   (= X19 false)
#   (= X10 false)
#   (= X11 false)
#   (= X12 false)
#   (= X13 false)
#   (= X14 false)
#   (= X15 false)
#   (= X16 false)
#   (= X17 false)
#   (= X29 false)
#   (= X28 false)
#   is not in any W
# Since we know that we don't have to deal with the above state, we will exclude it.
excluded_state = {}
for id in xrange(0, roadLength*roadWidth):
    excluded_state['X'+str(id)] = False

ret = rhtlpprob.validate(excluded_state=excluded_state)
print ret

if ret:
    # Synthesize automatons for each short horizon problem.
    aut_list = []
    for shprob in rhtlpprob.shprobs:
        aut_list.append(shprob.synthesizePlannerAut())

    # Generate graph of all automatons.
    output = congexf.dumpGexf(aut_list)
    destfile = 'acar_example.gexf'
    try:
        f = open(destfile, "w")
        f.write(output)
        f.close()
    except IOError:
        f.close()
        print "Error: could not write " + destfile + " to file."
    
    # Display graph?
    if raw_input("Do you want to open in Gephi? (y/n)") == 'y':
        try:
            print "Opening GEXF file in Gephi."
            call(["gephi", destfile])
        except:
            print "Failed to open " + destfile + " in Gephi. Try:\n\n" + \
                  "gephi " + destfile + "\n\n"


# if sp_auts is False:
#     print 'Error: rhtlp prob instance failed validation check.'
# else:
#     for sp_aut in sp_auts:
#         sp_aut.writeDotFile(sp_aut.__jtlvfile[:-4]+'.dot')
