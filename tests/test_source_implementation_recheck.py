import math
import numpy as np

from harness.evaluator import _tvd, _statevector_distance


def test_tvd_agrees_with_hand_computed_distributions():
    assert math.isclose(_tvd({'00':0.5,'11':0.5},{'00':0.8,'11':0.2}),0.3,abs_tol=1e-12)
    assert _tvd({'00':1.0},{'11':1.0}) == 1.0
    assert _tvd({'00':0.25,'11':0.75},{'00':0.25,'11':0.75}) == 0.0


def test_pilot_fidelity_cutoff_is_not_primary_distance_cutoff():
    distance_threshold=0.05
    exact_fidelity_cutoff=(1-distance_threshold**2/2)**2
    pilot_cutoff=0.9975
    assert math.isclose(exact_fidelity_cutoff,0.9975015625,abs_tol=1e-12)
    fidelity=(pilot_cutoff+exact_fidelity_cutoff)/2
    actual=np.array([math.sqrt(fidelity),math.sqrt(1-fidelity)],complex)
    expected=np.array([1,0],complex)
    assert not fidelity<pilot_cutoff  # The pilot mutation detector does not kill it.
    assert _statevector_distance(actual,expected)>distance_threshold


def test_current_qft_input_set_does_not_cover_other_column_phases():
    dft=np.exp(2j*np.pi*np.outer(np.arange(8),np.arange(8))/8)/math.sqrt(8)
    phases=np.eye(8);phases[2,2]=-1
    mutant=dft@phases
    basis=[np.eye(8)[:,j] for j in range(8)]
    selected=[np.array([1,1,0,0,0,0,0,0])/math.sqrt(2),
              np.array([1,1j,0,0,0,0,0,0])/math.sqrt(2)]
    fidelity=lambda a,b:float(abs(np.vdot(a,b))**2)
    assert all(math.isclose(fidelity(mutant@state,dft@state),1,abs_tol=1e-12)
               for state in basis+selected)
    unseen=np.array([1,0,1,0,0,0,0,0])/math.sqrt(2)
    assert fidelity(mutant@unseen,dft@unseen)<1e-12
