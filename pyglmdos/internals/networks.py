"""
Network models expose a probability of connection and a scale of the weights
"""
import abc

import numpy as np

from pyglmdos.abstractions import Component

from pyglm.deps.pybasicbayes.util.stats import sample_discrete_from_log
from pyglm.deps.pybasicbayes.util.stats import sample_niw

# from pyhawkes.internals.distributions import Discrete, Bernoulli, \
#                                              Gamma, Dirichlet, Beta

# TODO: Make a base class for networks

class _StochasticBlockModelBase(Component):
    """
    A stochastic block model is a clustered network model with
    K:          Number of nodes in the network
    C:          Number of blocks
    m[c]:       Probability that a node belongs block c
    p[c,c']:    Probability of connection from node in block c to node in block c'
    v[c,c']:    Scale of the gamma weight distribution from node in block c to node in block c'

    It is parameterized by:
    pi:         Parameter of Dirichlet prior over m
    tau0, tau1: Parameters of beta prior over p
    alpha:      Shape parameter of gamma prior over v
    beta:       Scale parameter of gamma prior over v
    """

    __metaclass__ = abc.ABCMeta

    def __init__(self, population,
                 C=1,
                 c=None, m=None, pi=1.0,
                 p=None, tau0=0.1, tau1=0.1,
                 mu=None, Sigma=None, mu0=0.0, kappa0=1.0, nu0=1.0, Sigma0=1.0,
                 allow_self_connections=True):
        """
        Initialize SBM with parameters defined above.
        """
        self.population = population
        self.N = self.population.N
        self.B = self.population.B

        assert isinstance(C, int) and C >= 1, "C must be a positive integer number of blocks"
        self.C = C

        if isinstance(pi, (int, float)):
            self.pi = pi * np.ones(C)
        else:
            assert isinstance(pi, np.ndarray) and pi.shape == (C,), "pi must be a sclar or a C-vector"
            self.pi = pi

        self.tau0    = tau0
        self.tau1    = tau1
        self.mu0     = mu0
        self.kappa0  = kappa0
        self.Sigma0  = Sigma0
        self.nu0     = nu0

        self.allow_self_connections = allow_self_connections

        if m is not None:
            assert isinstance(m, np.ndarray) and m.shape == (C,) \
                   and np.allclose(m.sum(), 1.0) and np.amin(m) >= 0.0, \
                "m must be a length C probability vector"
            self.m = m
        else:
            self.m = np.random.dirichlet(self.pi)


        if c is not None:
            assert isinstance(c, np.ndarray) and c.shape == (self.N,) and c.dtype == np.int \
                   and np.amin(c) >= 0 and np.amax(c) <= self.C-1, \
                "c must be a length K-vector of block assignments"
            self.c = c.copy()
        else:
            self.c = np.random.choice(self.C, p=self.m, size=(self.N))

        if p is not None:
            if np.isscalar(p):
                assert p >= 0 and p <= 1, "p must be a probability"
                self._p = p * np.ones((C,C))

            else:
                assert isinstance(p, np.ndarray) and p.shape == (C,C) \
                       and np.amin(p) >= 0 and np.amax(p) <= 1.0, \
                    "p must be a CxC matrix of probabilities"
                self._p = p
        else:
            self._p = np.random.beta(self.tau1, self.tau0, size=(self.C, self.C))

        if mu is not None and Sigma is not None:
            assert isinstance(mu, np.ndarray) and mu.shape == (C,C,self.B), \
                "mu must be a CxCxB array of mean weights"
            self._mu = mu

            assert isinstance(Sigma, np.ndarray) and Sigma.shape == (C,C,self.B,self.B), \
                "Sigma must be a CxCxBxB array of weight covariance matrices"
            self._Sigma = Sigma

        else:
            # Sample from the normal inverse Wishart prior
            self._mu = np.zeros((C, C, self.B))
            self._Sigma = np.zeros((C, C, self.B, self.B))
            for c1 in xrange(self.C):
                for c2 in xrange(self.C):
                    self._mu[c1,c2,:], self._Sigma[c1,c2,:,:] = \
                        sample_niw(self.mu0, self.Sigma0, self.kappa0, self.nu0)

        # If m, p, and v are specified, then the model is fixed and the prior parameters
        # are ignored
        if None not in (c, p, mu, Sigma):
            self.fixed = True
        else:
            self.fixed = False

    @property
    def P(self):
        """
        Get the KxK matrix of probabilities
        :return:
        """
        P = self._p[np.ix_(self.c, self.c)]
        if not self.allow_self_connections:
            np.fill_diagonal(P, 0.0)
        return P

    @property
    def Mu(self):
        """
        Get the NxNxB array of mean weights
        :return:
        """
        return self._mu[np.ix_(self.c, self.c, np.arange(self.B))]

    @property
    def Sigma(self):
        """
        Get the NxNxB array of mean weights
        :return:
        """
        return self._Sigma[np.ix_(self.c, self.c, np.arange(self.B), np.arange(self.B))]

    # def log_likelihood(self, x):
    #     """
    #     Compute the log likelihood of a set of SBM parameters
    #
    #     :param x:    (m,p,v) tuple
    #     :return:
    #     """
    #     m,p,v,c = x
    #
    #     lp = 0
    #     lp += Dirichlet(self.pi).log_probability(m)
    #     lp += Beta(self.tau1 * np.ones((self.C, self.C)),
    #                self.tau0 * np.ones((self.C, self.C))).log_probability(p).sum()
    #     lp += Gamma(self.mu0, self.Sigma0).log_probability(v).sum()
    #     lp += (np.log(m)[c]).sum()
    #     return lp
    #
    # def log_probability(self):
    #     return self.log_likelihood((self.m, self._p, self.v, self.c))

class GibbsSBM(_StochasticBlockModelBase):
    """
    Implement Gibbs sampling for SBM
    """
    def __init__(self, population,
                 C=1,
                 c=None, pi=1.0, m=None,
                 p=None, tau0=0.1, tau1=0.1,
                 mu=None, Sigma=None, mu0=0.0, kappa0=1.0, nu0=1.0, Sigma0=1.0,
                 allow_self_connections=True):

        super(GibbsSBM, self).__init__(population,
                                       C=C,
                                       c=c, pi=pi, m=m,
                                       p=p, tau0=tau0, tau1=tau1,
                                       mu=mu, Sigma=Sigma, mu0=mu0, kappa0=kappa0, Sigma0=Sigma0, nu0=nu0,
                                       allow_self_connections=allow_self_connections)

        # Initialize parameter estimates
        # print "Uncomment GibbsSBM init"
        # if not self.fixed:
        #     self.c = np.random.choice(self.C, size=(self.N))
        #     self.m = 1.0/C * np.ones(self.C)
        #     # self.p = self.tau1 / (self.tau0 + self.tau1) * np.ones((self.C, self.C))
        #     self._p = np.random.beta(self.tau1, self.tau0, size=(self.C, self.C))
        #     # self.v = self.alpha / self.beta * np.ones((self.C, self.C))
        #     self.v = np.random.gamma(self.mu0, 1.0/self.Sigma0, size=(self.C, self.C))

    def resample_p(self, A):
        """
        Resample p given observations of the weights
        """
        for c1 in xrange(self.C):
            for c2 in xrange(self.C):
                Ac1c2 = A[np.ix_(self.c==c1, self.c==c2)]

                if not self.allow_self_connections:
                    # TODO: Account for self connections
                    pass

                tau1 = self.tau1 + Ac1c2.sum()
                tau0 = self.tau0 + (1-Ac1c2).sum()
                self._p[c1,c2] = np.random.beta(tau1, tau0)

    def resample_mu_Sigma(self, A, W):
        """
        Resample v given observations of the weights
        """
        # import pdb; pdb.set_trace()
        for c1 in xrange(self.C):
            for c2 in xrange(self.C):
                Ac1c2 = A[np.ix_(self.c==c1, self.c==c2)]
                Wc1c2 = W[np.ix_(self.c==c1, self.c==c2)]
                alpha = self.mu0 + Ac1c2.sum() * self.kappa
                beta  = self.Sigma0 + Wc1c2[Ac1c2 > 0].sum()
                self.v[c1,c2] = np.random.gamma(alpha, 1.0/beta)

    def resample_c(self, A, W):
        """
        Resample block assignments given the weighted adjacency matrix
        and the impulse response fits (if used)
        """
        if self.C == 1:
            return

        # Sample each assignment in order
        for k in xrange(self.N):
            # Compute unnormalized log probs of each connection
            lp = np.zeros(self.C)

            # Prior from m
            lp += np.log(self.m)

            # Likelihood from network
            for ck in xrange(self.C):
                c_temp = self.c.copy().astype(np.int)
                c_temp[k] = ck

                # p(A[k,k'] | c)
                lp[ck] += Bernoulli(self._p[ck, c_temp])\
                                .log_probability(A[k,:]).sum()

                # p(A[k',k] | c)
                lp[ck] += Bernoulli(self._p[c_temp, ck])\
                                .log_probability(A[:,k]).sum()

                # p(W[k,k'] | c)
                lp[ck] += (A[k,:] * Gamma(self.kappa, self.v[ck, c_temp])\
                                .log_probability(W[k,:])).sum()

                # p(W[k,k'] | c)
                lp[ck] += (A[:,k] * Gamma(self.kappa, self.v[c_temp, ck])\
                                .log_probability(W[:,k])).sum()

                # TODO: Subtract of self connection since we double counted

                # TODO: Get probability of impulse responses g

            # Resample from lp
            self.c[k] = sample_discrete_from_log(lp)

    def resample_m(self):
        """
        Resample m given c and pi
        """
        pi = self.pi + np.bincount(self.c, minlength=self.C)
        self.m = np.random.dirichlet(pi)

    def resample(self, augmented_data):
        return

        # if self.fixed:
        #     return
        #
        # A = self.population.weight_model.A
        # W = self.population.weight_model.W
        #
        # self.resample_p(A)
        # self.resample_mu_Sigma(A, W)
        # self.resample_c(A, W)
        # self.resample_m()