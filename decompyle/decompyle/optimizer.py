"""A bytecode optimizer transliterated from compile.c to ease maintenance.

$Id: optimizer.py 82 2006-10-21 00:54:34Z spencermah $""" 

import opcode
from array import array
    
COMPATIBILITY = True
MAX_CONST_FOLD_SIZE = 20
    
        
def markblocks(codestr):
    """Identify blocks within which code may be safely altered.  See
    ISBASICBLOCK for the use cases"""
    
    from .se import (
        HAS_JUMP,
        GETJUMPTGT,
        HAVE_ARGUMENT)
        
    blocks = [0] * len(codestr)
    i = 0
    codelen = len(codestr)
    while i<codelen:
        op = codestr[i]
        if op in HAS_JUMP:
            j = GETJUMPTGT(codestr, i)
            blocks[j] = 1
        i+=(3 if (op>=HAVE_ARGUMENT) else 1)
    i=0
    blockcnt=0
    while i<codelen:
        blockcnt+=blocks[i]
        blocks[i] = blockcnt
        i+=1
    return blocks
    

class OptimizerError(Exception): pass


def optimize(codestr_orig, lnotab, consts, names, name="", firstlineno = 0):
    """Copy of compile.c opimizations, principally intended to enable code
    comparison tests to work. 
    
    Note the cases are mutually exclusive (so could be re-ordered).
    """
    
    from .se import (
        # opcodes used here
        NOP,
        RETURN_VALUE,
        JUMP_IF_FALSE, JUMP_IF_TRUE, 
        JUMP_FORWARD, 
        JUMP_ABSOLUTE, CONTINUE_LOOP,
        EXTENDED_ARG,
        POP_TOP,
        UNARY_NOT,
        UNARY_NEGATIVE,
        COMPARE_OP,
        BINARY_FLOOR_DIVIDE,
        BINARY_TRUE_DIVIDE,
        
        LOAD_NAME, LOAD_GLOBAL, LOAD_CONST,
        
        BUILD_TUPLE, BUILD_LIST, COMPARE_OP, UNPACK_SEQUENCE,
        ROT_TWO, ROT_THREE,
        
        # helper funcs - these are originally C macros
        GETARG, SETARG, GETJUMPTGT,
        
        # opcode maps/sets
        HAVE_ARGUMENT,
        HAS_JUMP,
        HAS_COND_JUMP,
        HAS_DIRECT_JUMP,
        HAS_UNCONDITIONAL_JUMP,
        HAS_REL_JUMP,
        HAS_ABS_JUMP,
        BINOPS,
        UNARY_OPS,
        )
        
    ISBASICBLOCK = lambda blocks, start,i: blocks[start] == blocks[start+i-1]
    
    NOP_CELL = array('B',(NOP,))
    
    codestr = array('B', codestr_orig) # operate on a copy
    codelen = len(codestr)
    tabsiz = len(lnotab)
    
    blocks = markblocks(codestr)
    addrmap = [0]*codelen
    
    try:
        
        if 255 in lnotab:
            raise OptimizerError('lnotab too complicated')
        elif codelen > 32700:
            raise OptimizerError('code too big (>32700 characters)')
        elif codestr[-1] != RETURN_VALUE:
            raise OptimizerError('code does not end with RETURN_VALUE')
        
        cumlc=0 # cumulative LOAD_CONSTS
        i = 0

        while i<codelen:
            
            # Note, unlike the compile.c, which increments i using
            # CODE_SIZE[codestr[i]], we use the faster expression at
            # the end of the loop: i += 1 + 2*op>HAVE_ARGUMENT
            # However, this means that if an opcode is changed in place,
            # op must be updated too.  Subtle bug potential!
            
            
            lastlc = cumlc
            cumlc = 0;
            op = codestr[i]
            
            # Replace UNARY_NOT JUMP_IF_FALSE POP_TOP with 
            # JUMP_IF_TRUE POP_TOP */
            # This appears not to work in compile.c
            if op == UNARY_NOT:
                if (codestr[i+1] == JUMP_IF_FALSE  and
                        codestr[i+4] == POP_TOP  and
                        ISBASICBLOCK(blocks,i,5)):
                    tgt = GETJUMPTGT(codestr, (i+1))
                    if (codestr[tgt] == POP_TOP):
                        j = GETARG(codestr, i+1) + 1
                        op = codestr[i] = JUMP_IF_TRUE
                        SETARG(codestr, i, j)
                        codestr[i+3] = POP_TOP
                        codestr[i+4] = NOP
                        
            # not a is b -->  a is not b
            # not a in b -->  a not in b
            # not a is not b -->  a is b
            # not a not in b -->  a in b
            elif op == COMPARE_OP:
                j = GETARG(codestr, i)
                if 6 <= j <= 9 and codestr[i+3] == UNARY_NOT and \
                        ISBASICBLOCK(blocks,i,4):

                    SETARG(codestr, i, (j^1))
                    codestr[i+3] = NOP

            # Replace LOAD_GLOBAL/LOAD_NAME None with LOAD_CONST None
            elif op == LOAD_NAME or op == LOAD_GLOBAL:
                j = GETARG(codestr, i)
                if names[j] == 'None':
                    if (not COMPATIBILITY) or (None in consts):
                        # CPython won't add None
                        
                        op = codestr[i] = LOAD_CONST
                        SETARG(codestr, i, consts.index_or_add(None))
                        cumlc = lastlc + 1
                    
            # Skip over LOAD_CONST trueconst JUMP_IF_FALSE xx  POP_TOP */
            elif op == LOAD_CONST:
                cumlc = lastlc + 1;
                j = GETARG(codestr, i);
                if (codestr[i+3] == JUMP_IF_FALSE  and
                        codestr[i+6] == POP_TOP  and
                        ISBASICBLOCK(blocks, i, 7) and
                        consts[j]):
                    codestr[i:i+7] = NOP_CELL*7 
                    cumlc = 0;
                    

            # Try to fold tuples of constants (includes a case for lists
            # which are only used for "in" and "not in" tests).
            # Skip over BUILD_SEQN 1 UNPACK_SEQN 1.
            # Replace BUILD_SEQN 2 UNPACK_SEQN 2 with ROT2.
            # Replace BUILD_SEQN 3 UNPACK_SEQN 3 with ROT3 ROT2.
            elif op == BUILD_TUPLE or op == BUILD_LIST:
                j = GETARG(codestr, i)
                h = i - 3 * j;

                if h >= 0  and j <= lastlc and (
                (op == BUILD_TUPLE and ISBASICBLOCK(blocks, h, 3*(j+1)))
                or (op == BUILD_LIST and codestr[i+3]==COMPARE_OP and \
                ISBASICBLOCK(blocks, h, 3*(j+2)) and (6<=GETARG(codestr, i+3)<=7))):
                    
                    # in-line tuple_of_constants(codestr, h, j, consts)
                    
                    end = h + j*3
                    newconst = []

                    combined_const = tuple(consts[GETARG(codestr,i)] 
                                    for i in range(h, end, 3))

                    new_arg = consts.add(combined_const, force_append = COMPATIBILITY)


                    # Write NOPs over old LOAD_CONSTS and
                    # add a new LOAD_CONST newconst on top of the BUILD_TUPLE n */

                    codestr[h:end] = NOP_CELL*(j*3)
                    codestr[end] = LOAD_CONST;
                    SETARG(codestr, end, new_arg) # compile.c doesn't check to see i
                    # new constant already exists, so this will diverge in some cases                
                    
                    
                    assert(codestr[i] == LOAD_CONST)
                    cumlc = 1
                    
                elif (codestr[i+3] == UNPACK_SEQUENCE  and
                    ISBASICBLOCK(blocks, i, 6) and
                    j == GETARG(codestr, i+3)):
                        
                    if j == 1:
                        codestr[i:i+6] = NOP_CELL*6
                    elif j == 2:
                        op = codestr[i] = ROT_TWO
                        codestr[i+1:i+6] = NOP_CELL*5
                    elif j == 3:
                        op = codestr[i] = ROT_THREE
                        codestr[i+1] = ROT_TWO
                        codestr[i+2:i+6] = NOP_CELL*4
                
            # Fold binary ops on constants.
            # LOAD_CONST c1 LOAD_CONST c2 BINOP -->  LOAD_CONST binop(c1,c2)
            
            elif op in BINOPS:
                # BINOPS maps op:function
                if (lastlc >= 2	 and ISBASICBLOCK(blocks, i-6, 7)):
                    # inline fold_binops_on_constants(&codestr[i-6], consts))
                    start = i-6
                    #consts_tuple = consts.inorder()
                    const1 = consts[GETARG(codestr, start)]
                    const2 = consts[GETARG(codestr, start+3)]
                    # compile.c does not have this test - how does it avoid
                    # crashing on /0?
                    try:
                        new_const = BINOPS[op](const1, const2)
                    except (TypeError, ZeroDivisionError, ValueError):
                        pass
                    else:
                        size = 0
                        if hasattr(new_const,"__len__"):
                            size = len(new_const)
                        if size <= MAX_CONST_FOLD_SIZE:
                            # compile.c does a size check?  what is this?
                            i = start+4 # ~ i-=2
                            codestr[start:i] = NOP_CELL*4
                            
                            op = codestr[i]=LOAD_CONST # op = 
                            # here, compile.c just appends to consts
                            SETARG(codestr, i, consts.add(new_const, force_append = COMPATIBILITY))
                            cumlc = 1

            # Fold unary ops on constants.
            # LOAD_CONST c1  UNARY_OP -->	LOAD_CONST unary_op(c) */
            elif op in UNARY_OPS:
                # UNARY_OPS maps opcode:function
                if lastlc >= 1 and ISBASICBLOCK(blocks, i-3, 4):
                    # inline fold_unaryops_on_constants
                    start = i-3
                    const1 = consts[GETARG(codestr, start)]
                    if const1 or op != UNARY_NEGATIVE:
                        # Don't negate -0.0
                        new_const = UNARY_OPS[op](const1)
                        i = start+1
                        codestr[start] = NOP
                        op = codestr[i] = LOAD_CONST
                        SETARG(codestr, i, consts.add(new_const, force_append = COMPATIBILITY))
                        cumlc = 1
        
            #   Simplify conditional jump to conditional jump where the
            #   result of the first test implies the success of a similar
            #   test or the failure of the opposite test.
            #   Arises in code like:
            #   "if a and b:"
            #   "if a or b:"
            #   "a and b or c"
            #   "(a and b) and c"
            #   x:JUMP_IF_FALSE y   y:JUMP_IF_FALSE z  -->  x:JUMP_IF_FALSE z
            #   x:JUMP_IF_FALSE y   y:JUMP_IF_TRUE z	 -->  x:JUMP_IF_FALSE y+3
            #   where y+3 is the instruction following the second test.
            elif op == JUMP_IF_FALSE or op == JUMP_IF_TRUE:
                tgt = GETJUMPTGT(codestr, i)
                j = codestr[tgt]
                if j == JUMP_IF_FALSE or j == JUMP_IF_TRUE:
                    if j == op:
                        tgttgt = GETJUMPTGT(codestr, tgt) - i - 3
                        SETARG(codestr, i, tgttgt)
                    else:
                        tgt -= i
                        SETARG(codestr, i, tgt)
                        
                if j in HAS_DIRECT_JUMP:
                    tgttgt = GETJUMPTGT(codestr, tgt)
                    if op == JUMP_FORWARD:
                        op = JUMP_ABSOLUTE
                    if op not in HAS_ABS_JUMP:
                        tgttgt -= (i+3)
                    if tgttgt >= 0:
                        codestr[i] = op
                        SETARG(codestr, i, tgttgt)                        
                    
            # Untested?            
            elif op in HAS_UNCONDITIONAL_JUMP:
                tgt = GETJUMPTGT(codestr, i)

                if codestr[tgt] in HAS_DIRECT_JUMP:
                    tgttgt = GETJUMPTGT(codestr, tgt)
                    if op == JUMP_FORWARD:
                        op = JUMP_ABSOLUTE
                    if op not in HAS_ABS_JUMP:
                        tgttgt -= (i+3)
                    if tgttgt >= 0:
                        codestr[i] = op
                        SETARG(codestr, i, tgttgt)
                        
            elif op == EXTENDED_ARG:
                raise OptimizerError("Found EXTENDED_ARG")
                        
            elif op == RETURN_VALUE:
                if (i+4 < codelen and codestr[i+4] == RETURN_VALUE 
                        and ISBASICBLOCK(blocks, i, 5)):
                    for j in range(i+1, i+5):
                        codestr[j] = NOP
                        
            i += 1 + 2*(op>=HAVE_ARGUMENT)    
                 
        # Fixup linenotab
        nops = 0
        i=0
        while i<codelen:
            addrmap[i] = i-nops
            op = codestr[i]
            nops += (op==NOP)
            i += 1 + 2*(op>=HAVE_ARGUMENT)
           
        cum_orig_line = 0
        last_line = 0

        i=0
        while i<tabsiz:
            cum_orig_line += lnotab[i]
            new_line = addrmap[cum_orig_line]
            assert new_line - last_line < 255
            lnotab[i] = (new_line - last_line)
            last_line = new_line
            i+=2
           
        i=h=0
        while i<codelen:
            op=codestr[i]
            if op == NOP:
                i+=1
                continue
            elif op in HAS_ABS_JUMP:
                j = addrmap[GETARG(codestr, i)]
                SETARG(codestr, i, j)
            elif op in HAS_REL_JUMP:
                j=addrmap[GETARG(codestr, i)+i+3]-addrmap[i]-3
                SETARG(codestr, i, j)
            adj = 1 + 2*(op>=HAVE_ARGUMENT)
            codestr[h:h+adj] = codestr[i:i+adj]
            i+=adj; h+=adj
           
        assert h+nops == codelen
        del codestr[h:]         
    except OptimizerError:
        pass
        # bail out
    else:
        # copy the code back
        codestr_orig[:] = codestr
