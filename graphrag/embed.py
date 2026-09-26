"""bge-small-en-v1.5 (33M parameters) through ONNX Runtime on CPU: the encoder for the vector index.
Chunks are cut at 256 tokens."""
import hashlib

import numpy as np

from . import data


class Embedder:
    def __init__(self, threads=4, max_tokens=256):
        import onnxruntime as ort
        from tokenizers import Tokenizer
        folder = data.embedder_dir()
        self.tokenizer = Tokenizer.from_file(str(folder / "tokenizer.json"))
        self.tokenizer.enable_truncation(max_length=max_tokens)
        self.tokenizer.enable_padding(pad_id=0, pad_token="[PAD]")
        options = ort.SessionOptions()
        options.intra_op_num_threads = options.inter_op_num_threads = threads
        self.session = ort.InferenceSession(str(folder / "model_optimized.onnx"), options, providers=["CPUExecutionProvider"])
        self.inputs = {i.name for i in self.session.get_inputs()}

    def encode(self, texts, batch=32):
        order = np.argsort([len(t) for t in texts], kind="stable")     # similar lengths together: less padding
        texts = [texts[i] for i in order]
        out = []
        for i in range(0, len(texts), batch):
            enc = self.tokenizer.encode_batch(list(texts[i:i + batch]))
            ids = np.array([e.ids for e in enc], dtype=np.int64)
            mask = np.array([e.attention_mask for e in enc], dtype=np.int64)
            feeds = {"input_ids": ids, "attention_mask": mask}
            if "token_type_ids" in self.inputs:
                feeds["token_type_ids"] = np.zeros_like(ids)
            v = self.session.run(None, feeds)[0][:, 0]                    # CLS pooling
            out.append(v / np.linalg.norm(v, axis=1, keepdims=True))
        vectors = np.vstack(out).astype(np.float32)
        result = np.empty_like(vectors)
        result[order] = vectors
        return result

    def cached(self, texts):
        key = hashlib.sha256("\x00".join(texts).encode()).hexdigest()[:16]
        path = data.cache_dir() / f"embeddings-{key}.npy"
        if not path.exists():
            np.save(path, self.encode(texts))
        return np.load(path)
