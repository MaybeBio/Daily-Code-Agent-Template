#!/usr/bin/env python
# coding: utf-8

# In[2]:


# This Python 3 environment comes with many helpful analytics libraries installed
# It is defined by the kaggle/python Docker image: https://github.com/kaggle/docker-python
# For example, here's several helpful packages to load



import sys
#sys.path.append('/kaggle/input/zidingyi-xiuendata1')
import argparse
import configparser
import os
import random
import sys
from dataclasses import dataclass
from typing import List, Tuple, Dict, Any, Optional

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.nn.functional as F
import torchmetrics
from torch.autograd import Variable
from torch.utils.data import DataLoader, Subset
from torchmetrics.classification import (
    BinaryF1Score, BinaryRecall, BinaryPrecision,
    BinarySpecificity, BinaryAccuracy, BinaryAUROC
)
from transformers import (
    AutoTokenizer, AutoModelForTokenClassification, AutoConfig,
    BertTokenizer, BertModel, BertForTokenClassification, BertConfig,
    get_linear_schedule_with_warmup
)
from sklearn.model_selection import KFold

# Custom imports
import tqdm
from bert_optimization import BertAdam
from dataloader import EntDataset, get_data


parser = argparse.ArgumentParser()
parser.add_argument('--dropo', default=0.1, type=float, help='Dropout rate')
parser.add_argument('--lr', default='1e-5', type=float, help='Learning rate')
parser.add_argument('--BATCH_SIZE', default=1, type=int, help='Batch size')


ner_file_path = './data/9pcy_train.csv'

parser.add_argument('--task', default='epi', type=str, help='Task name')

parser.add_argument('--model_path', default="Rostlab/prot_bert", type=str, help='Model path')
#parser.add_argument('--model_path', default="facebook/esm2_t30_150M_UR50D", type=str, help='Model path')
#parser.add_argument('--model_path', default="facebook/esm2_t12_35M_UR50D", type=str, help='Model path')
parser.add_argument('--is_weight', default=1, type=int, help='Whether to use weighted loss')

args = parser.parse_known_args()[0]


task = args.task
EPOCH = 20
BATCH_SIZE = args.BATCH_SIZE
dropo = args.dropo
lr = args.lr
model_path = args.model_path
is_weight = args.is_weight
maxlen = 1024


device = torch.device("cuda")


if args.is_weight == 1:
    weights_dict = {
        'epi':[1.,5],
        '1coe':[1,10],
        '1am7': [1., 5]
    }
    weights1 = weights_dict.get(task, [1., 1.])

random_seed = 681
torch.manual_seed(random_seed)
np.random.seed(random_seed)
random.seed(random_seed)
os.environ['PYTHONHASHSEED'] = str(random_seed)
np.random.seed(random_seed)
torch.manual_seed(random_seed)
torch.cuda.manual_seed(random_seed)
torch.cuda.manual_seed_all(random_seed)
torch.backends.cudnn.deterministic = True

torch.backends.cudnn.benchmark = False

f1fun = BinaryF1Score(ignore_index=-100).to(device)
recallfun = BinaryRecall(ignore_index=-100).to(device)
precisionfun = BinaryPrecision(ignore_index=-100).to(device)
specificityfun = BinarySpecificity(ignore_index=-100).to(device)
accfun = BinaryAccuracy(ignore_index=-100).to(device)
aucfun = BinaryAUROC(thresholds=None, ignore_index=-100).to(device)

f1fun1 = BinaryF1Score(ignore_index=-100).to(device)
recallfun1 = BinaryRecall(ignore_index=-100).to(device)
precisionfun1 = BinaryPrecision(ignore_index=-100).to(device)
specificityfun1 = BinarySpecificity(ignore_index=-100).to(device)
accfun1 = BinaryAccuracy(ignore_index=-100).to(device)
aucfun1 = BinaryAUROC(thresholds=None, ignore_index=-100).to(device)
aucfuneval = BinaryAUROC(thresholds=None, ignore_index=-100).to(device)


if 'esm' in model_path:
    tokenizer = AutoTokenizer.from_pretrained(model_path, do_lower_case=False)
    model_config = AutoConfig.from_pretrained(model_path)
    model = AutoModelForTokenClassification.from_pretrained(model_path, num_labels=2, classifier_dropout=dropo)
else:
    tokenizer = BertTokenizer.from_pretrained(model_path, do_lower_case=False)
    model_config = BertConfig.from_pretrained(model_path)
    model = BertForTokenClassification.from_pretrained(model_path, num_labels=2, classifier_dropout=dropo, ignore_mismatched_sizes=True)



class epi_ant(nn.Module):
    def __init__(self, model, model_config, dim_result=2):
        super(epi_ant, self).__init__()
        self.model = model

    def forward(self, batch_token, batch_attention_mask):
        out = self.model(input_ids=batch_token, attention_mask=batch_attention_mask)
        return out['logits']

net = epi_ant(model, model_config)
net.to(device)

def set_optimizer(model, train_steps=None, lr=2e-5):
    param_optimizer = list(model.named_parameters())
    param_optimizer = [n for n in param_optimizer if 'pooler' not in n[0]]
    no_decay = ['bias', 'LayerNorm.bias', 'LayerNorm.weight']
    optimizer_grouped_parameters = [
        {'params': [p for n, p in param_optimizer if not any(nd in n for nd in no_decay)], 'weight_decay': 0.01},
        {'params': [p for n, p in param_optimizer if any(nd in n for nd in no_decay)], 'weight_decay': 0.0}
    ]
    optimizer = BertAdam(optimizer_grouped_parameters, lr=lr, warmup=0.1, t_total=train_steps)
    return optimizer
class EarlyStopping:
    def __init__(self, patience=4, verbose=False):
        self.patience = patience
        self.verbose = verbose
        self.counter = 0
        self.best_score = None
        self.early_stop = False

    def __call__(self, score, model):
    #def __call__(self, score, model, model_path):   
        if self.best_score is None:
            self.best_score = score
            #self.save_checkpoint(model, model_path)
        elif score < self.best_score:
            self.counter += 1
            if self.counter >= self.patience:
                self.early_stop = True
        else:
            self.best_score = score
            #self.save_checkpoint(model, model_path)
            self.counter = 0


"""
    def save_checkpoint(self, model, model_path):
        torch.save(model.state_dict(), model_path)
        if self.verbose:
            print(f'Saving model to {model_path}')
"""



from sklearn.model_selection import train_test_split

#ner_file_path = '/kaggle/input/all37-datafold/Group_9/1hel_train.csv'
ner_data = get_data(ner_file_path)


train_sequences, val_sequences = train_test_split(
    ner_data,
    test_size=0.1,
    random_state=42,
)


train_subset = EntDataset(train_sequences, tokenizer, max_len=maxlen)
val_subset = EntDataset(val_sequences, tokenizer, max_len=maxlen)

ner_loader_train = DataLoader(train_subset, batch_size=BATCH_SIZE, collate_fn=train_subset.collate, shuffle=True)
ner_loader_val = DataLoader(val_subset, batch_size=BATCH_SIZE, collate_fn=val_subset.collate, shuffle=False)


total_steps = len(ner_loader_train) * EPOCH
optimizer = set_optimizer(net, train_steps=total_steps, lr=lr)
scheduler = get_linear_schedule_with_warmup(optimizer, num_warmup_steps=0, num_training_steps=total_steps)
early_stopping = EarlyStopping(patience=3, verbose=True)#Early stopping strategy
accuracy = torchmetrics.Accuracy(task='binary', ignore_index=-100).to(device)


if is_weight == 1:
    weights = weights1
    class_weights = torch.FloatTensor(weights).to(device)
    loss_fun = nn.CrossEntropyLoss(weight=class_weights, ignore_index=-100)
else:
    loss_fun = nn.CrossEntropyLoss(ignore_index=-100)

aucmax = 0.
besteo = 0.
for eo in range(EPOCH):  # epoch
    total_loss = 0.0
    for idx, batch in tqdm.tqdm(enumerate(ner_loader_train)):
        raw_text_list, labels, input_ids, attention_mask = batch
        input_ids, attention_mask, labels = input_ids.to(device), attention_mask.to(device), labels.to(device)
        out = net(input_ids, attention_mask)
        out = out[:, 1:-1, ]
        b, l, n = out.size()
        attention_mask = attention_mask[:, 1:-1, ]
        labels = labels + (attention_mask - 1) * 100

        loss = loss_fun(out.reshape(-1, out.shape[-1]), labels.reshape(-1).long())
        total_loss += loss.item()
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()
        scheduler.step()


        f1 = f1fun(out.argmax(dim=-1), labels.long())
        recall = recallfun(out.argmax(dim=-1), labels.long())
        precision = precisionfun(out.argmax(dim=-1), labels.long())
        specificity = specificityfun(out.argmax(dim=-1), labels.long())
        acc = accfun(out.argmax(dim=-1), labels.long())
        auc = aucfun(out[:, :, 1], labels.long())


    mean_loss = total_loss / len(ner_loader_train)
    f1mean = f1fun.compute()
    recallmean = recallfun.compute()
    precisionmean = precisionfun.compute()
    specificitymean = specificityfun.compute()
    accmean = accfun.compute()
    aucmean = aucfun.compute()
    print(f'train epoch:{eo} mean_loss:{mean_loss:.3f} auc:{aucmean:.3f} acc:{accmean:.3f} f1:{f1mean:.3f} recall:{recallmean:.3f} precision:{precisionmean:.3f}')


    f1fun.reset()
    recallfun.reset()
    precisionfun.reset()
    specificityfun.reset()
    accfun.reset()
    aucfun.reset()

    #validation
    with torch.no_grad():
        eval_total_loss = 0.0
        net.eval()
        f1all = 0
        f1all = 0
        recallall = 0
        precisionall = 0
        specificityall = 0
        accall = 0
        for idx, batch in tqdm.tqdm(enumerate(ner_loader_val)):
            raw_text_list, labels, input_ids, attention_mask= batch
            input_ids, attention_mask,  labels = input_ids.to(device), attention_mask.to(device),  labels.to(device)
            out = net(input_ids, attention_mask)
            out = out[:, 1:-1:, ]
            attention_mask=attention_mask[:,1:-1:,] 
            labels=labels+(attention_mask-1)*100
            b, l, n = out.size()
            eval_loss = loss_fun(out.reshape(b * l, -1), labels.reshape(-1).long())
            eval_total_loss = eval_total_loss + eval_loss
            eval_mean_loss = eval_total_loss / (idx + 1)


            auc1 = aucfun1(out[:, :, 1], labels.long())
            auceval = aucfuneval(out[:, :, 1], labels.long())
            f11 = f1fun1(out.argmax(dim=-1), labels.long())
            recall1 = recallfun1(out.argmax(dim=-1), labels.long())
            precision1 = precisionfun1(out.argmax(dim=-1), labels.long())
            specificity1 = specificityfun1(out.argmax(dim=-1), labels.long())
            acc1 = accfun1(out.argmax(dim=-1), labels.long())

            #Select the best threshold
            f1all1 = 0
            a = torch.arange(-100, 100, 1) / 100
            for num, cuts in enumerate(a):
                cut = float(cuts)
                f1 = torch.tensor(f1fun(torch.where(out[:, :, 1] > cut, 1, 0), labels.long())).unsqueeze(dim=0)
                recall = torch.tensor(recallfun(torch.where(out[:, :, 1] > cut, 1, 0), labels.long())).unsqueeze(dim=0)
                precision = torch.tensor(precisionfun(torch.where(out[:, :, 1] > cut, 1, 0), labels.long())).unsqueeze(dim=0)
                specificity = torch.tensor(specificityfun(torch.where(out[:, :, 1] > cut, 1, 0), labels.long())).unsqueeze(dim=0)
                acc = torch.tensor(accfun(torch.where(out[:, :, 1] > cut, 1, 0), labels.long())).unsqueeze(dim=0)
                auc = aucfun(out[:, :, 1], labels.long())
                if num == 0.:
                    f1all1 = f1
                    recallall1=recall
                    precisionall1 = precision
                    specificityall1 = specificity
                    accall1 = acc
                else:
                    f1all1 = torch.cat((f1all1, f1), dim=0)
                    recallall1 = torch.cat((recallall1, recall), dim=0)
                    precisionall1 = torch.cat((precisionall1, precision), dim=0)
                    specificityall1 = torch.cat((specificityall1, specificity), dim=0)
                    accall1 = torch.cat((accall1, acc), dim=0)

            if idx == 0:
                f1all = f1all1
                recallall=recallall1
                precisionall = precisionall1
                specificityall = specificityall1
                accall = accall1
            else:
                f1all = f1all + f1all1
                recallall = recallall1+recallall
                precisionall = precisionall1 + precisionall
                specificityall = specificityall1 + specificityall
                accall = accall1 + accall
        print('f1meanmax', torch.max(f1all / (idx + 1)))
        weizhi = torch.argmax(f1all)
        yuzhi = a[weizhi]
        print('yuzhi', weizhi, yuzhi)


        f1mean1 = f1fun1.compute()
        recallmean1 = recallfun1.compute()
        precisionmean1 = precisionfun1.compute()
        specificitymean1 = specificityfun1.compute()
        accmean1 = accfun1.compute() 

        aucmean1 = aucfun1.compute()
        aucevalmean=aucfuneval.compute()


    if aucmax <= aucevalmean:
        aucmax = aucevalmean
        besteo = eo 
        best_model_state = net.state_dict()
    """
        outevaljiezhi = [
        fold,
        round(aucmean1.cpu().item(), 4),
        round((accall[weizhi] / (idx + 1)).cpu().item(), 4),
        round(torch.max(f1all / (idx + 1)).cpu().item(), 4),
        round((recallall[weizhi] / (idx + 1)).cpu().item(), 4),
        round((precisionall[weizhi] / (idx + 1)).cpu().item(), 4),
        round((specificityall[weizhi] / (idx + 1)).cpu().item(), 4),
        ]
    """
    outevalzidong = [
        round(aucmean1.cpu().item(), 4),
        round(accmean1.cpu().item(), 4),
        round(f1mean1.cpu().item(), 4),
        round(recallmean1.cpu().item(), 4),
        round(precisionmean1.cpu().item(), 4),
        round(specificitymean1.cpu().item(), 4),
        ]



    print("\n")
    print("eval epoch:%d\t  auc:%.3f acc:%.3f f1:%.3f rec:%.3f prec:%.3f spec:%.3f" % 
      (eo, aucmean1, accmean1, f1mean1, recallmean1, precisionmean1, specificitymean1))

    early_stopping(aucevalmean, net)                                   

    if early_stopping.early_stop:
        print(f"Early stopping triggered, epoch={eo}_dropo={dropo}_lr={lr}")
        break

    f1fun1.reset()
    recallfun1.reset()
    precisionfun1.reset()
    specificityfun1.reset()
    accfun1.reset()
    aucfun1.reset()
    aucfuneval.reset()


os.makedirs('./checkpoints', exist_ok=True)
model_save_path = f'./checkpoints/val_model_besteo_{besteo}_dp_{dropo}_lr_{lr}_bz_{BATCH_SIZE}.pkl'
torch.save(best_model_state, model_save_path)
print(f"Best model for Fold saved at {model_save_path}") 

