__author__ = 'aviv'

from theano import tensor as Tensor
from theano import scan as scan
import theano.tensor.nlinalg as nlinalg

from regularization_base import RegularizationBase
from MISC.container import ContainerRegisterMetaClass


class PairWiseCorrelationRegularization(RegularizationBase):

    __metaclass__ = ContainerRegisterMetaClass

    def __init__(self, regularization_parameters):
        super(PairWiseCorrelationRegularization, self).__init__(regularization_parameters)

        self.euc_length = bool(int(regularization_parameters['euc_length']))
        self.pair_wise = bool(int(regularization_parameters['pair_wise_correlation']))
        self.variance = bool(int(regularization_parameters['variance']))
        self.corr = bool(int(regularization_parameters['corr']))
        self.reg1 = float(regularization_parameters['regularization_param1'])
        self.reg2 = float(regularization_parameters['regularization_param2'])

    def compute(self, symmetric_double_encoder, params):

        regularization = 0;

        for layer in symmetric_double_encoder:

            forward = layer.output_forward
            backward = layer.output_backward

            forward_centered = (forward - Tensor.mean(forward, axis=0)).T
            backward_centered = (backward - Tensor.mean(backward, axis=0)).T

            forward_var = Tensor.dot(forward_centered, forward_centered.T) + self.reg1 * Tensor.eye(forward_centered.shape[0])
            backward_var = Tensor.dot(backward_centered, backward_centered.T) + self.reg2 * Tensor.eye(backward_centered.shape[0])

            e11 = self._compute_square_chol(forward_var, layer.hidden_layer_size)
            e22 = self._compute_square_chol(backward_var, layer.hidden_layer_size)
            e12 = Tensor.dot(forward_centered, backward_centered.T)

            corr = Tensor.dot(Tensor.dot(e11, e12), e22)

            if self.euc_length:
                regularization += ((forward_centered - backward_centered) ** 2).sum()
                print 'added euc reg'

            if self.pair_wise:
                regularization += ((forward_var - Tensor.eye(forward.shape[0], dtype=Tensor.config.floatX)) ** 2).sum()
                regularization += ((backward_var - Tensor.eye(backward.shape[0], dtype=Tensor.config.floatX)) ** 2).sum()
                print 'added pair reg'

            if self.variance:
                regularization -= forward_var.sum()
                regularization -= backward_var.sum()
                print 'added var reg'

            if self.corr:
               regularization += Tensor.sqrt(Tensor.sum(corr))



        return self.weight * regularization


    def print_regularization(self, output_stream):

        super(PairWiseCorrelationRegularization, self).print_regularization(output_stream)

    def _compute_square_chol(self, a, n):

        w, v = Tensor.nlinalg.eigh(a,'L')

        result, updates = scan(lambda eigs, eigv, prior_results, size: Tensor.sqrt(eigs) * Tensor.dot(eigv.reshape([1, size]), eigv.reshape([size, 1])),
                               outputs_info=Tensor.zeros_like(a),
                               sequences=[w, v.T],
                               non_sequences=n)

        return result


