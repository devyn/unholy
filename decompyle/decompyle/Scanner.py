#  Copyright (c) 1999 John Aycock
#  Copyright (c) 2000-2002 by hartmut Goebel <hartmut@goebel.noris.de>
#
#  See main module for license.
#

__all__ = ['Token', 'Scanner', 'getscanner']

import types
import dis
import re

class Token:
    """
    Class representing a byte-code token.

    A byte-code token is equivalent to the contents of one line
    as output by dis.dis().
    """
    def __init__(self, type, attr=None, pattr=None, offset=-1):
        self.type = intern(type)
        self.attr = attr #oparg
        self.pattr = pattr # oparg's data,if load_const,this is string
        self.offset = offset # pos

    def __cmp__(self, o):
        if isinstance(o, Token):
            # both are tokens: compare type and pattr
            return cmp(self.type, o.type) or cmp(self.pattr, o.pattr)
        else:
            return cmp(self.type, o)

    def __repr__(self):		return str(self.type)
    def __str__(self):
        pattr = self.pattr or ''
        return '%s\t%-17s %r' % (self.offset, self.type, pattr)
    def __hash__(self):		return hash(self.type)
    def __getitem__(self, i):	raise IndexError


class Code:
    """
    Class for representing code-objects.

    This is similar to the original code object, but additionally
    the diassembled code is stored in the attribute '_tokens'.
    """
    def __init__(self, co, scanner):
        for i in dir(co):
            if i.startswith('co_'):
                setattr(self, i, getattr(co, i))
        self._tokens, self._customize = scanner.disassemble(co)

class Scanner:
    def __init__(self, version):
        self.__version = version

        self.resetTokenClass()

        self.JUMP_OPs = map(lambda op: dis.opname[op],
                            dis.hasjrel + dis.hasjabs)

    def setShowAsm(self, showasm, out=None):
        self.showasm = showasm
        self.out = out

    def setTokenClass(self, tokenClass):
        assert type(tokenClass) == types.ClassType
        self.Token = tokenClass

    def resetTokenClass(self):
        self.setTokenClass(Token)

    def disassemble(self, co):
        """
        Disassemble a code object, returning a list of 'Token'.

        The main part of this procedure is modelled after
        dis.disassemble().
        """
        rv = []
        #other info such ad make_fun_1...
        #because create function use other info
        customize = {}
        Token = self.Token # shortcut

        code = co.co_code
        cf = self.find_jump_targets(code)
        n = len(code)
        i = 0
        extended_arg = 0
        free = None
        while i < n:
            offset = i
            if cf.has_key(offset):
                for j in range(cf[offset]):
                    rv.append(Token('COME_FROM',
                                    offset="%s_%d" % (offset, j) ))

            c = code[i]
            op = ord(c)
            opname = dis.opname[op]
            i += 1
            oparg = None; pattr = None
            if op >= dis.HAVE_ARGUMENT:
                oparg = ord(code[i]) + ord(code[i+1]) * 256 + extended_arg
                extended_arg = 0
                i += 2
                if op == dis.EXTENDED_ARG:
                    extended_arg = oparg * 65536L
                if op in dis.hasconst:
                    const = co.co_consts[oparg]
                    if type(const) == types.CodeType:
                        oparg = const
                        lambdaReg= re.compile(r'<lambda.*>')
                        if lambdaReg.match(const.co_name):
                            assert opname == 'LOAD_CONST'
                            opname = 'LOAD_LAMBDA'
                        # verify uses 'pattr' for comparism, since 'attr'
                        # now holds Code(const) and thus can not be used
                        # for comparism (todo: think about changing this)
                        #pattr = 'code_object @ 0x%x %s->%s' %\
                        #	(id(const), const.co_filename, const.co_name)
                        pattr = 'code_object ' + const.co_name
                    else:
                        pattr = const
                elif op in dis.hasname:
                    pattr = co.co_names[oparg]
                elif op in dis.hasjrel:
                    pattr = repr(i + oparg)
                elif op in dis.hasjabs:
                    pattr = repr(oparg)
                elif op in dis.haslocal:
                    pattr = co.co_varnames[oparg]
                elif op in dis.hascompare:
                    pattr = dis.cmp_op[oparg]
                elif op in dis.hasfree:
                    if free is None:
                        free = co.co_cellvars + co.co_freevars
                    pattr = free[oparg]

            if opname == 'SET_LINENO':
                continue
            elif opname in ('BUILD_LIST', 'BUILD_TUPLE', 'BUILD_SLICE',
                            'UNPACK_LIST', 'UNPACK_TUPLE', 'UNPACK_SEQUENCE',
                            'MAKE_FUNCTION', 'CALL_FUNCTION', 'MAKE_CLOSURE',
                            'CALL_FUNCTION_VAR', 'CALL_FUNCTION_KW',
                            'CALL_FUNCTION_VAR_KW', 'DUP_TOPX',
                            ):
                opname = '%s_%d' % (opname, oparg)
                customize[opname] = oparg

            rv.append(Token(opname, oparg, pattr, offset))

        if self.showasm:
            out = self.out # shortcut
            for t in rv:
                print >>out, t
            print >>out

        return rv, customize


    def find_jump_targets(self, code):
        """
        Detect all offsets in a byte code which are jump targets.

        Return the list of offsets.

        This procedure is modelled after dis.findlables(), but here
        for each target the number of jumps are counted.
        """
        HAVE_ARGUMENT = dis.HAVE_ARGUMENT
        hasjrel = dis.hasjrel
        #hasjabs = dis.hasjabs

        targets = {}
        n = len(code)
        i = 0
        while i < n:
            c = code[i]
            op = ord(c)
            #print "do " + dis.opname[op]
            i += 1
            if op >= HAVE_ARGUMENT:
                oparg = ord(code[i]) + ord(code[i+1]) * 256
                i += 2
                label = -1
                if op in hasjrel:
                    label = i + oparg
                # todo: absolut jumps
                #elif op in hasjabs:
                #    label = oparg
                if label >= 0:
                    targets[label] = targets.get(label, 0) + 1
        return targets


__scanners = {}

def getscanner(version):
    if not __scanners.has_key(version):
        __scanners[version] = Scanner(version)
    return __scanners[version]

# local variables:
# tab-width: 4
