#!/bin/bash
# The desk's models on the Luckfox Lyra (32-bit ARM), as install.sh does on the Orange Pi: sherpa-onnx's linux-arm-gnueabihf build
# (its libonnxruntime.so also serves embed.py, through onnxruntime/ here, copied to ~/.models/shared/python/onnxruntime/).
set -euo pipefail
REL=https://github.com/k2-fsa/sherpa-onnx/releases/download
SHERPA=sherpa-onnx-v1.13.8-linux-arm-gnueabihf-shared
PARAKEET=sherpa-onnx-nemo-parakeet_tdt_transducer_110m-en-36000-int8
STT=~/.models/transcribe; CMP=~/.models/compare/all-minilm-l6-v2
HF=https://huggingface.co/Xenova/all-MiniLM-L6-v2/resolve/main
mkdir -p $STT ~/.models/compare
if [ ! -d $STT/lib ]; then rm -rf $STT/.new; mkdir $STT/.new
  curl -fsSL "$REL/v1.13.8/$SHERPA.tar.bz2" | tar xj -C $STT/.new --strip-components=1
  mv $STT/.new/bin $STT/.new/lib $STT/; rm -rf $STT/.new; echo "sherpa done"; fi
[ -f $STT/silero_vad.onnx ] || { curl -fsSL -o $STT/.vad "$REL/asr-models/silero_vad.onnx"; mv $STT/.vad $STT/silero_vad.onnx; echo "vad done"; }
if [ ! -f $CMP/model_quantized.onnx ]; then rm -rf $CMP.new; mkdir $CMP.new
  curl -fsSL -o $CMP.new/tokenizer.json "$HF/tokenizer.json"; curl -fsSL -o $CMP.new/model_quantized.onnx "$HF/onnx/model_quantized.onnx"
  mv $CMP.new $CMP; echo "minilm done"; fi
if [ ! -d $STT/parakeet-tdt-110m ]; then rm -rf $STT/.p; mkdir $STT/.p
  curl -fsSL "$REL/asr-models/$PARAKEET.tar.bz2" | tar xj -C $STT/.p --strip-components=2 --wildcards '*.onnx' '*/tokens.txt'
  mv $STT/.p $STT/parakeet-tdt-110m; echo "parakeet done"; fi
echo ALL DONE
