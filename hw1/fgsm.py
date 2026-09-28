import torch
import torch.nn as nn


# fix seed so that random initialization always performs the same 
torch.manual_seed(13)


# create the model N as described in the question
N = nn.Sequential(nn.Linear(10, 10, bias=False),
                  nn.ReLU(),
                  nn.Linear(10, 10, bias=False),
                  nn.ReLU(),
                  nn.Linear(10, 3, bias=False))

# random input
x = torch.rand((1,10)) # the first dimension is the batch size; the following dimensions the actual dimension of the data
x.requires_grad_() # this is required so we can compute the gradient w.r.t x

t = 1 # target class

epsReal = 0.5  #depending on your data this might be large or small
eps = epsReal - 1e-7 # small constant to offset floating-point erros

# The network N classfies x as belonging to class 2
original_class = N(x).argmax(dim=1).item()  # TO LEARN: make sure you understand this expression
print("Original Class: ", original_class)
assert(original_class == 2)


def iter_fsgm(t=1, alpha=0.25, num_iter=100):
    L = nn.CrossEntropyLoss()
    adv_x = x.clone().detach()

    for iteration in range(num_iter):

        adv_x.requires_grad_(True)
        loss = L(N(adv_x), torch.tensor([t], dtype=torch.long))
        N.zero_grad()
        loss.backward()

        with torch.no_grad():
            adv_x = adv_x - alpha * adv_x.grad.sign()
            adv_x = x + torch.clamp(adv_x - x, -eps, eps)
        adv_x = adv_x.detach()

        new_class = N(adv_x).argmax(dim=1).item()
        if new_class == t:
            print(f"Iterative FGSM succeeded at iteration {iteration + 1}")
            return adv_x, new_class
    return adv_x, new_class

# compute gradient
# note that CrossEntropyLoss() combines the cross-entropy loss and an implicit softmax function
L = nn.CrossEntropyLoss()
loss = L(N(x), torch.tensor([t], dtype=torch.long)) # TO LEARN: make sure you understand this line
loss.backward()

# your code here
# adv_x should be computed from x according to the fgsm-style perturbation such that the new class of xBar is the target class t above
# hint: you can compute the gradient of the loss w.r.t to x as x.grad
adv_x = x - eps * x.grad.sign()

single_step_class = N(adv_x).argmax(dim=1).item()
print("New Class in Single-step FGSM: ", single_step_class)

# targeted FGSM with alpha=0.25 and the original radius epsReal=0.5.
adv_x, new_class = iter_fsgm(t=t, alpha=0.25)
print("New Class in Iterative FGSM: ", new_class)

assert(new_class == t)
# it is not enough that adv_x is classified as t. We also need to make sure it is 'close' to the original x. 
print(torch.norm((x-adv_x),  p=float('inf')).data)
assert( torch.norm((x-adv_x), p=float('inf')) <= epsReal)

l_d = torch.norm((x-adv_x), p=float('inf'))
print(f'more specific x-adv_x: {l_d}')
