"""onnxruntime, the part embed.py uses, for a 32-bit ARM board with no onnxruntime wheel (Luckfox Lyra).

It calls the libonnxruntime.so that sherpa-onnx's linux-arm-gnueabihf build ships (onnxruntime 1.28) through its C
API (ctypes): InferenceSession(path, options).run(None, {name: int64 array}) -> [float32 arrays], get_inputs(), and
SessionOptions.intra_op_num_threads. The positions in the OrtApi table are from onnxruntime_c_api.h 1.28.0; the
table only grows, so they hold for any later library.
"""
import ctypes as C
import os

import numpy as np

LIB = os.environ.get("ORT_LIB") or os.path.join(os.environ.get("DESK_MODELS", os.path.expanduser("~/.models")),
                                                "transcribe", "lib", "libonnxruntime.so")
API_VERSION = 28
AT = dict(GetErrorMessage=2, CreateEnv=3, CreateSession=7, Run=9, CreateSessionOptions=10,
          SetSessionGraphOptimizationLevel=23, SetIntraOpNumThreads=24, SetInterOpNumThreads=25,
          SessionGetInputCount=30, SessionGetOutputCount=31, SessionGetInputName=36, SessionGetOutputName=37,
          CreateTensorWithDataAsOrtValue=49, GetTensorMutableData=51, GetDimensionsCount=61, GetDimensions=62,
          GetTensorTypeAndShape=65, CreateCpuMemoryInfo=69, AllocatorFree=76, GetAllocatorWithDefaultOptions=78,
          ReleaseStatus=93, ReleaseMemoryInfo=94, ReleaseValue=96, ReleaseTensorTypeAndShapeInfo=99)
P, S = C.c_void_p, C.c_size_t
SIG = dict(GetErrorMessage=(C.c_char_p, P), CreateEnv=(P, C.c_int, C.c_char_p, C.POINTER(P)),
           CreateSession=(P, P, C.c_char_p, P, C.POINTER(P)),
           Run=(P, P, P, C.POINTER(C.c_char_p), C.POINTER(P), S, C.POINTER(C.c_char_p), S, C.POINTER(P)),
           CreateSessionOptions=(P, C.POINTER(P)), SetSessionGraphOptimizationLevel=(P, P, C.c_int),
           SetIntraOpNumThreads=(P, P, C.c_int), SetInterOpNumThreads=(P, P, C.c_int),
           SessionGetInputCount=(P, P, C.POINTER(S)), SessionGetOutputCount=(P, P, C.POINTER(S)),
           SessionGetInputName=(P, P, S, P, C.POINTER(C.c_char_p)), SessionGetOutputName=(P, P, S, P, C.POINTER(C.c_char_p)),
           CreateTensorWithDataAsOrtValue=(P, P, P, S, C.POINTER(C.c_int64), S, C.c_int, C.POINTER(P)),
           GetTensorMutableData=(P, P, C.POINTER(P)), GetDimensionsCount=(P, P, C.POINTER(S)),
           GetDimensions=(P, P, C.POINTER(C.c_int64), S), GetTensorTypeAndShape=(P, P, C.POINTER(P)),
           CreateCpuMemoryInfo=(P, C.c_int, C.c_int, C.POINTER(P)), AllocatorFree=(P, P, P),
           GetAllocatorWithDefaultOptions=(P, C.POINTER(P)), ReleaseStatus=(None, P), ReleaseMemoryInfo=(None, P),
           ReleaseValue=(None, P), ReleaseTensorTypeAndShapeInfo=(None, P))
TYPES = {np.dtype(np.float32): 1, np.dtype(np.int64): 7, np.dtype(np.int32): 6}


class _Api:
    def __init__(self):
        lib = C.CDLL(LIB)
        lib.OrtGetApiBase.restype = C.POINTER(P * 2)
        get_api = C.CFUNCTYPE(P, C.c_uint32)(lib.OrtGetApiBase().contents[0])
        table = C.cast(get_api(API_VERSION), C.POINTER(P * 512)).contents
        for name, at in AT.items():
            restype, *args = SIG[name]
            setattr(self, name, C.CFUNCTYPE(restype, *args)(table[at]))
        self.lib = lib

    def check(self, status):
        if status:
            why = self.GetErrorMessage(status).decode()
            self.ReleaseStatus(status)
            raise RuntimeError(why)


_api, _env = None, None


def _start():
    global _api, _env
    if _api is None:
        _api = _Api()
        env = P()
        _api.check(_api.CreateEnv(3, b"desk", C.byref(env)))  # 3: warnings shown, info and verbose not
        _env = env
    return _api


class SessionOptions:
    def __init__(self):
        self.intra_op_num_threads = 0
        self.inter_op_num_threads = 0


class NodeArg:
    def __init__(self, name):
        self.name = name


class InferenceSession:
    def __init__(self, path, sess_options=None, providers=None):
        api = _start()
        options = P()
        api.check(api.CreateSessionOptions(C.byref(options)))
        so = sess_options or SessionOptions()
        if so.intra_op_num_threads:
            api.check(api.SetIntraOpNumThreads(options, so.intra_op_num_threads))
        if so.inter_op_num_threads:
            api.check(api.SetInterOpNumThreads(options, so.inter_op_num_threads))
        self.session = P()
        api.check(api.CreateSession(_env, os.fsencode(path), options, C.byref(self.session)))
        allocator = P()
        api.check(api.GetAllocatorWithDefaultOptions(C.byref(allocator)))
        self.inputs, self.outputs = self._names(api.SessionGetInputCount, api.SessionGetInputName, allocator), \
            self._names(api.SessionGetOutputCount, api.SessionGetOutputName, allocator)
        self.memory = P()
        api.check(api.CreateCpuMemoryInfo(0, 0, C.byref(self.memory)))  # device allocator, default memory

    def _names(self, count, name_at, allocator):
        n = S()
        _api.check(count(self.session, C.byref(n)))
        out = []
        for i in range(n.value):
            name = C.c_char_p()
            _api.check(name_at(self.session, i, allocator, C.byref(name)))
            out.append(name.value.decode())
        return out

    def get_inputs(self):
        return [NodeArg(n) for n in self.inputs]

    def get_outputs(self):
        return [NodeArg(n) for n in self.outputs]

    def run(self, output_names, feed):
        api = _api
        wanted = list(output_names or self.outputs)
        arrays = {k: np.ascontiguousarray(v) for k, v in feed.items()}
        values = []
        try:
            for name, a in arrays.items():
                value, shape = P(), (C.c_int64 * a.ndim)(*a.shape)
                api.check(api.CreateTensorWithDataAsOrtValue(self.memory, a.ctypes.data, a.nbytes, shape, a.ndim,
                                                              TYPES[a.dtype], C.byref(value)))
                values.append(value)
            names_in = (C.c_char_p * len(arrays))(*[k.encode() for k in arrays])
            names_out = (C.c_char_p * len(wanted))(*[k.encode() for k in wanted])
            outs = (P * len(wanted))()
            api.check(api.Run(self.session, None, names_in, (P * len(values))(*values), len(values), names_out, len(wanted), outs))
            result = []
            for value in outs:
                info, n = P(), S()
                api.check(api.GetTensorTypeAndShape(value, C.byref(info)))
                api.check(api.GetDimensionsCount(info, C.byref(n)))
                dims = (C.c_int64 * n.value)()
                api.check(api.GetDimensions(info, dims, n.value))
                api.ReleaseTensorTypeAndShapeInfo(info)
                data = P()
                api.check(api.GetTensorMutableData(value, C.byref(data)))
                count = int(np.prod(list(dims))) if n.value else 1
                result.append(np.ctypeslib.as_array(C.cast(data, C.POINTER(C.c_float)), (count,)).reshape(list(dims)).copy())
                api.ReleaseValue(value)
            return result
        finally:
            for value in values:
                api.ReleaseValue(value)


def get_available_providers():
    return ["CPUExecutionProvider"]
