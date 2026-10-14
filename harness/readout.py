"""Canonical quantum-bit readout for full terminal measurements."""
from collections import Counter

EVALUATOR_VERSION = "evaluation_policy_v4"


class ReadoutError(ValueError):
    """A circuit does not expose an unambiguous full terminal readout."""


def prepare_readout(qc):
    """Full terminal-readout projection, rejecting ambiguous mappings."""
    circuit=qc.copy();mapping={};targets=set();seen=False
    for item in circuit.data:
        name=item.operation.name
        if name=='barrier':continue
        if name=='measure':
            seen=True;q=circuit.find_bit(item.qubits[0]).index;c=circuit.find_bit(item.clbits[0]).index
            if q in mapping or c in targets:raise ReadoutError('repeated measurement or overwritten classical bit')
            mapping[q]=c;targets.add(c)
        elif seen or item.clbits or getattr(item.operation,'condition',None) is not None:
            raise ReadoutError('nonterminal or classically controlled circuit')
    if not mapping:
        offset=circuit.num_clbits;circuit.measure_all()
        mapping={q:offset+q for q in range(circuit.num_qubits)}
    if len(mapping)!=circuit.num_qubits:raise ReadoutError('partial measurement')
    return circuit,mapping


def project_counts(counts,mapping,n_clbits):
    result=Counter()
    for key,count in counts.items():
        bits=key.replace(' ','')
        if len(bits)!=n_clbits or set(bits)-{'0','1'}:raise ReadoutError('unexpected count key')
        projected=''.join(bits[n_clbits-1-mapping[q]] for q in reversed(range(len(mapping))))
        result[projected]+=count
    total=sum(result.values())
    return {key:value/total for key,value in result.items()}
