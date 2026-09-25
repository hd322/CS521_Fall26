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

num_iter = 20
alpha = (epsReal - 1e-7) / num_iter

def iter_fsgm(t=1, alpha=0.01, num_iter=10):
    adv_x = x.clone().detach()

    L = nn.CrossEntropyLoss()
    for i in range(num_iter):
        adv_x.requires_grad_(True)

        loss = L(N(adv_x), torch.tensor([t], dtype=torch.long))

        N.zero_grad()
        loss.backward()
        
        with torch.no_grad():
            adv_x = adv_x - alpha * adv_x.grad.sign()
            adv_x = torch.max(torch.min(adv_x, x + eps), x - eps)
        adv_x = adv_x.detach()

    new_class = N(adv_x).argmax(dim=1).item()
    print("New Class in Multi-step fgsm: ", new_class)
    # print(torch.norm((x-adv_x), p=float('inf')).data)

    return adv_x, new_class

def margin_loss(logits, t):
    target_logit = logits[0, t]
    other = logits.clone()
    other[0, t] = -1e9 
    max_other = other.max()
    return max_other - target_logit


def pgd_attack(t=1, alpha=0.01, num_iter=100, num_restarts=10, CE=False):
    L = nn.CrossEntropyLoss()
    for i in range(num_restarts):
        delta = (torch.rand_like(x) * 2 - 1) * eps
        adv_x = torch.max(torch.min(x + delta, x + eps), x - eps).detach()
        for j in range(num_iter):
            adv_x.requires_grad_(True)
            if CE == True:
                loss = L(N(adv_x), torch.tensor([t], dtype=torch.long))
                loss_type = "CrossEntropyLoss"
            else:
                logits = N(adv_x)
                loss = margin_loss(logits, t)
                loss_type = "margin_loss"
            N.zero_grad()
            loss.backward()
            with torch.no_grad():
                adv_x = adv_x - alpha * adv_x.grad.sign()
                adv_x = torch.max(torch.min(adv_x, x + eps), x - eps)
            adv_x = adv_x.detach()
        pred_class = N(adv_x).argmax(dim=1).item()
        if pred_class == t:
            print(f"New Class in PGD: {pred_class}")
            print(f"[INFO] Success at restart {i+1}, iter {j+1}, Loss Type is {loss_type}")
            return adv_x, pred_class
    print(f"New Class in PGD with {loss_type}: {pred_class}")
    return adv_x, -1 

# compute gradient
# note that CrossEntropyLoss() combines the cross-entropy loss and an implicit softmax function
L = nn.CrossEntropyLoss()
loss = L(N(x), torch.tensor([t], dtype=torch.long)) # TO LEARN: make sure you understand this line
loss.backward()

# your code here
# adv_x should be computed from x according to the fgsm-style perturbation such that the new class of xBar is the target class t above
# hint: you can compute the gradient of the loss w.r.t to x as x.grad
adv_x = x - eps * x.grad.sign()

# single_step fgsm
new_class = N(adv_x).argmax(dim=1).item()
print("New Class: ", new_class)

# multi_step fgsm
adv_x, new_class = iter_fsgm(alpha=alpha, num_iter=num_iter)

# PGD
adv_x, new_class = pgd_attack(CE=True)

adv_x, new_class = pgd_attack()

assert(new_class == t)
# it is not enough that adv_x is classified as t. We also need to make sure it is 'close' to the original x. 
print(torch.norm((x-adv_x),  p=float('inf')).data)
assert( torch.norm((x-adv_x), p=float('inf')) <= epsReal)

print("====== ======\n")
val = torch.norm((x-adv_x), p=float('inf')).item()
print(f'more specific x-adv_x: {val}')
