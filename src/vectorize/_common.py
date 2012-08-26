import numpy as np
from llvm_cbuilder import shortnames as _C
from numbapro import _internal
from numbapro.translate import Translate


_llvm_ty_str_to_numpy = {
            'i8'     : np.int8,
            'i16'    : np.int16,
            'i32'    : np.int32,
            'i64'    : np.int64,
            'float'  : np.float32,
            'double' : np.float64,
        }

def _llvm_ty_to_numpy(ty):
    return _llvm_ty_str_to_numpy[str(ty)]

class CommonVectorizeFromFrunc(object):
    def build(self, lfunc):
        raise NotImplementedError

    def __call__(self, lfunclist, engine, **kws):
        '''create ufunc from a llvm.core.Function

        lfunclist : a single or iterable of llvm.core.Function instance
        engine : a llvm.ee.ExecutionEngine instance

        return a function object which can be called from python.
        '''
        try:
            iter(lfunclist)
        except TypeError:
            lfunclist = [lfunclist]


        ptrlist = self._prepare_pointers(lfunclist, engine, **kws)

        fntype = lfunclist[0].type.pointee
        inct = len(fntype.args)
        outct = 1

        tyslist = []

        get_typenum = lambda T:np.dtype(_llvm_ty_to_numpy(T)).num
        for lfunc in lfunclist:
            fntype = lfunc.type.pointee
            if len(fntype.args) != inct: # check argument counts
                raise TypeError("All functions must have equal number of arguments")

            assert fntype.return_type != _C.void

            tys = list(map(get_typenum, list(fntype.args) + [fntype.return_type]))
            tyslist.append(tys)

        datlist = [None] * len(lfunclist)

        # Becareful that fromfunc does not provide full error checking yet.
        # If typenum is out-of-bound, we have nasty memory corruptions.
        # For instance, -1 for typenum will cause segfault.
        # If elements of type-list (2nd arg) is tuple instead,
        # there will also memory corruption. (Seems like code rewrite.)
        ufunc = _internal.fromfunc(ptrlist, tyslist, inct, outct, datlist)
        return ufunc

    def _prepare_pointers(self, lfunclist, engine, **kws):
        # build all functions
        spuflist = [self.build(lfunc, **kws) for lfunc in lfunclist]

        # We have an engine, build ufunc

        try:
            ptr_t = long
        except:
            ptr_t = int
            assert False, "Have not check this yet" # Py3.0?

        ptrlist = []
        tyslist = []
        datlist = []
        for i, spuf in enumerate(spuflist):
            fptr = engine.get_pointer_to_function(spuf)
            ptrlist.append(ptr_t(fptr))

        return ptrlist

class GenericVectorize(object):
    def __init__(self, func):
        self.pyfunc = func
        self.translates = []

    def add(self, *args, **kwargs):
        t = Translate(self.pyfunc, *args, **kwargs)
        t.translate()
        self.translates.append(t)

    def _get_lfunc_list(self):
        return [t.lfunc for t in self.translates]

    def build_ufunc(self):
        raise NotImplementedError

def ufunc_core_impl(fnty, func, args, steps, item):
    get_offset = lambda B, S, T: B[item * S].reference().cast(_C.pointer(T))

    indata = []
    for i, argty in enumerate(fnty.args):
        ptr = get_offset(args[i], steps[i], argty)
        indata.append(ptr.load())

    out_index = len(fnty.args)
    outptr = get_offset(args[out_index], steps[out_index],
                        fnty.return_type)

    res = func(*indata)
    outptr.store(res)


