from sage.all import *


def prod(list,initial):
    #Forms the product of all elements of the list uses initial as the initial value
    result = initial
    for element in list:
        result *= element
    return result

#File to help compute chern classes and relations between that come up in my academic work


def exterior_power(n,p,algorithm="recursive",degree=None):
    #Returns the chern class of the pth exterior power of an n dimensional bundle E
    # in terms of the chern class of E
    #Optional algorithm property gives the algorithm used to decompose polynomial of line bundles
    # Naive corresponds to computing the full polynomial mostly used for testing
    #If positive degree is given just return the chern class less than that degree.

    #Polynomial ring of polynomials in the chern classes.
    chern_ring = PolynomialRing(RationalField(),'c',n+1) # N+1 gens as c_0 is 1 to get the dimensions to agree.
    #By the splitting principle this is the same as computing a decomposition into elementary
    # symmetric polynomials of the polynomial which is the product of
    # (1+x_{i_1}+...x_{i_p}) for each combination of 1<=i_1<..<i_p<=n.
    # We call such a polynomial a one combination polynomial in p and n.
    decomp = decompose_one_combination_polynomial(n,p,algorithm,degree)
    #Convert the decomposition into a polynomial in the chern classes.
    chern = chern_ring.zero()
    chern_gens = chern_ring.gens()
    monomial_coefficients = decomp.monomial_coefficients()
    #Directly convert elementary symmetric monomials to monomials in chern generators
    # Would like to do this with a hom
    for monomial in monomial_coefficients:
        coefficient = monomial_coefficients[monomial]
        #As all chern classes of E are zero in degree greater than n
        # only include those monomials containing elementary symmetric polynomials
        # with degree less than or equal to n.
        if all(degree <= n for degree in monomial):
            chern += coefficient*prod([chern_gens[i] for i in monomial], chern_ring.one())
    return chern


def clean_higher_terms(decomp,n):
    #Removes all the terms in decomp with a support containing e_i with i>n
    # if computing over n variables then such a e_i must be zero
    cleaned_decomp = decomp.parent().zero()
    for support in decomp.support():
        if len(support)==0 or max(support) <= n:
            cleaned_decomp += decomp.coefficient(support) * decomp.parent()[support]
    return cleaned_decomp

def filter_by_degree(decomp,degree):
    #Returns the homogenous part of the decomposition less than the given positive degree where the degree of e_i is i
    filtered_decomp = decomp.parent().zero()
    for support in decomp.support():
        if sum(support) < degree:
            filtered_decomp += decomp.coefficient(support) * decomp.parent()[support]
    return filtered_decomp

def filter_by_var_degree(var_decomp,degree):
    #Returns the homogenous part of a polynomial decomposition less than the given positive degree
    # where the degree of e_i is i and the degree of t is 1
    poly_ring = var_decomp.parent()
    t = poly_ring.gens()[0]
    filtered_decomp = poly_ring.zero()
    for i in xrange(var_decomp.degree()+1):
        if degree <= i:
            break
        filtered_decomp += t**i * filter_by_degree(var_decomp[i], degree-i)
    return filtered_decomp

def decomp_one_combination_polynomial_naive(n,p,degree):
    #Compute elementary symmetric decomposition the naive way compute the polynomial explicitly and decompose it
    # Using the inbuilt symmetric functions methods
    poly_ring = PolynomialRing(RationalField(),'x',n) # A ring with enough generators to work in.
    #Construct polynomial
    roots = [1+sum(c) for c in Combinations(poly_ring.gens(),p)]
    poly = prod(roots,poly_ring.one())
    #Get elementary symmetric decomposition
    elementary = SymmetricFunctions(RationalField()).elementary()
    decomp = clean_higher_terms(elementary.from_polynomial(poly),n)
    if degree:
        #If degree is present filter the decomposition to just return that component
        decomp = filter_by_degree(decomp,degree)
    return decomp


def degree_shift(decomp,degree):
    #Shift all elementary polynomials in decomposition by given degree
    shifted_decomp = decomp.parent().zero()
    for support in decomp.support():
        coefficient = decomp.coefficient(support)
        shifted_support = support[degree:]
        monomial = decomp.parent()[shifted_support]
        shifted_decomp += coefficient * monomial
    return shifted_decomp


def variable_unique_expansion_elementary(n,i,poly_ring):
    #Given an elementary symmetric polynomial in n variables gives the unique polynomial in a new variable t
    # such that the constant part is the ith symmetric polynomial and the polynomial is symmetric in the
    # variables t,x1,..,xn
    t = poly_ring.gens()[0]
    e = poly_ring.base_ring()
    return e[i] + t*e[i-1]


def variable_unique_expansion_decomposition(n,decomp,poly_ring):
    #Given an elementary symmetric polynomial decomposition in n variables gives the shifted by degree
    # unique polynomial in a new variable t such that the constant part is the given decomposition
    # and the polynomial is a symmetric decomposition in the variables t,x1,..,xn
    expansion = poly_ring.zero()
    for support in decomp.support():
        coefficient = decomp.coefficient(support)
        monomial = poly_ring.one()
        for el in support:
            monomial *= variable_unique_expansion_elementary(n, el, poly_ring)
        expansion += coefficient*monomial
    return expansion


def reduce_variable_decomposition(n,var_decomp):
    #Takes a symmetric decomposotion with an extra variable and converts it into a decomposition in a
    # new set of variables. In particular given a decomposition of q(t,x_1,x_2,..,x_n) of the form
    # sum(t^i * d_i(x_1,...,x_n) and returns a decomposition of q in t,x_1 ... x_n

    #Use the relation that e_i(x_1,...,x_n) = t.e_{i-1}(x_1...x_{n-1}) + e_i(x_1,..,x_{n-1})
    # under the relation t -> x_n
    #New polynmial ring to work in

    #From lowest degree of variable t to the highest reduce decomp by the unique expansion of this coeffieicent
    var_poly_ring = var_decomp.parent()
    t = var_poly_ring.gens()[0]
    elementary = var_poly_ring.base_ring()
    degree = 0  # current lowest degree
    reduced_decomp = elementary.zero() # current reduced decomposition
    while not var_decomp.is_zero():
        coefficient = var_decomp[degree]
        shifted_coefficient = degree_shift(coefficient,degree)
        unique_expand = variable_unique_expansion_decomposition(n,shifted_coefficient,var_poly_ring)
        #Reduce the variable decomposition by the expansion shifted to the required degree
        # add this level to th reduced decomposition shifted to the required degree
        var_decomp -= unique_expand*(t**degree)*(elementary[n-1]**degree)
        reduced_decomp += shifted_coefficient*(elementary[n]**degree)
        #Increase degree for next iteration
        degree += 1
    return clean_higher_terms(reduced_decomp,n)

_elementary_linear_extension_cache = {}


def linear_variable_elementary_extension(n,i):
    # returns a decomposition of the elementary symmetric polynomial e_i(t+x_1,...,t+x_n) as a polynomial in t
    # in particular it returns sum(t^i * d_i(x_1,...,x_n))
    #Use cache to save time as may be called often with same arguments
    if (n,i) in _elementary_linear_extension_cache:
        return _elementary_linear_extension_cache[(n,i)]
    #Construct the polynomial ring in a single variable t over the elementary symmetric algebra
    elementary = SymmetricFunctions(RationalField()).elementary()
    poly_ring = PolynomialRing(elementary,'t')
    t = poly_ring.gens()[0]
    #constuct as a sum of monomials in t
    extension = poly_ring.zero()
    mon_number = binomial(n, i) # number of monomials in e_i
    for j in xrange(i+1):
        monomial = (t**j) * elementary[i-j]
        #Number of monomials look at number of monomials x_1 ... x_{i-j}
        # number of x_1 ... x_{i-j} in expansion of a monomial of e_i
        # * number of monomials in e_i containing x_1...x_{i-j}
        coefficient = binomial(n-i+j,j)
        extension += coefficient*monomial
    #Write to cache and return
    cleaned_extension = extension.map_coefficients(lambda x:clean_higher_terms(x,n))
    _elementary_linear_extension_cache[(n,i)] = cleaned_extension
    return cleaned_extension


def linear_variable_decomposition_extension(n, decomp):
    #Takes a symmetric decomposition in of a polynomial q n variable x_1, .., ,x_n and
    # returns a decomposition of the polynomial q(t+x_1,...,t+x_n) as a polynomial in t
    # in particular it returns sum(t^i * d_i(x_1,...,x_n))

    #Construct the polynomial ring in a single variable t over the elementary symmetric algebra
    elementary = SymmetricFunctions(RationalField()).elementary()
    poly_ring = PolynomialRing(elementary, 't')
    #Ideally here we would use a hom but it is not well supported so fold over the monomials in decomp
    extension = poly_ring.zero()
    for support in decomp.support():
        monomial = poly_ring.one()
        for index in support:
            monomial *= linear_variable_elementary_extension(n,index)
        coefficient = decomp.coefficient(support)
        extension += coefficient * monomial
    cleaned_extension = extension.map_coefficients(lambda x:clean_higher_terms(x,n))
    return cleaned_extension


#Cache of previous smaller results to improve recursion
_combination_polynomial_cache = {}

def decompose_one_combination_polynomial_recursive(n,p,degree):
    #We perform this computation recursively based on the following note the combination polynomial of order p
    # q_p(x_1,...,x_n) can be split into the product of q_p(x_1,...,x_{n-1}) and the linear extension with the variable
    # x_n of the polynomial q_{p-1}(x_1,...,x_{n-1})

    #See if required data is in the cache
    if (n, p, degree) in _combination_polynomial_cache:
        return _combination_polynomial_cache[(n, p, degree)]
    #Elementary symmetric function algebra
    elementary = SymmetricFunctions(RationalField()).elementary()
    #Give results for base cases
    if p>n:
        #If p > n then the polynomial is trivial
        return filter_by_degree(elementary.zero())
    if p==0:
        #If p==0 then the polynomial == 1
        return filter_by_degree(elementary[[]])
    if p==1:
        #If p==1 then this is the defining polynmoial of the elementary symmetric polynomials
        #If degree is specified only return part with needed degree
        elem_sum = [elementary[i] for i in xrange(n+1)]
        return filter_by_degree(sum(elem_sum),degree)
    if p==n:
        #If p==n then only one combination is possible and q_n = 1+e_1
        return filter_by_degree(elementary[[0]]+elementary[[1]],degree)
    #Else recurse and get the decompositions of initial and tail roots
    #Get the full decomposition for now in the head and tail.
    tail_roots = decompose_one_combination_polynomial_recursive(n-1,p,degree)
    initial_part = decompose_one_combination_polynomial_recursive(n-1,p-1,degree)
    initial_roots = linear_variable_decomposition_extension(n-1,initial_part)
    #Renormalize as the extra variable is split between p-1 variables
    normalized_roots = initial_roots.parent().zero()
    t = initial_roots.parent().gens()[0]
    for i in xrange(initial_roots.degree()+1):
        coefficient = initial_roots[i]
        exponent = t * (1/(p-1)*elementary[[]])
        normalized_roots += coefficient*(exponent**i)
    #Remove higher unneeded parts from the decomp
    normalized_roots = filter_by_var_degree(normalized_roots,degree)
    #Recombine to get a decomposition of q_n
    full_decomp = normalized_roots * tail_roots
    #Remove extra variable to get a decomposition n terms of x_1,..,x_n
    #filter to roots by degree as the reduce functions preserves degree
    full_decomp = filter_by_var_degree(full_decomp,degree)
    decomp = reduce_variable_decomposition(n,full_decomp)
    #Reduce degree - should be redundant!
    decomp = filter_by_degree(decomp,degree)
    #Add to cache and return
    _combination_polynomial_cache[(n, p, degree)] = decomp
    return decomp


def decompose_one_combination_polynomial(n,p,algorithm="recursive",degree=None):
    #Optional algorithm property gives the algorithm used to decompose polynomial of line bundles
    # Naive corresponds to computing the full polynomial mostly used for testing
    #If positive degree is given only return the part of the decomposition less than that degree.

    #Default to a degree which returns everything.
    if degree:
        degree = binomial(n,p)+1
    if algorithm=="naive":
        return decomp_one_combination_polynomial_naive(n,p,degree)
    #Default to using recursive algorithm
    return decompose_one_combination_polynomial_recursive(n, p, degree)

#if __name__=="__main__":
    #print(exterior_power(4,2)) #Basic check