import json
import random
import torch
import pandas as pd
import numpy as np
from torch.utils.data import Dataset
def get_data(filename):
    yeast_prot_data = pd.read_csv(filename,index_col=False)
#yeast_prot_data = pd.read_csv("../input/ecoli-data/id-sol-seq_eSOL.csv",index_col=False)
    sequences_Example = list(yeast_prot_data["sequence"])
    sequences_Example = [i[3:-2] for i in sequences_Example]

    target =list(yeast_prot_data["interface"])
    #print('qian',target)
    target = [i[1:-1].replace('\n','') for i in target]
    #print('hou',target)
    target=[i.split(' ') for i in target]

    sequences_number = []
    for i in sequences_Example:
        sequences_number.append(len(i))

        new_prot_character = []
    for prot_seq in sequences_Example:
        linshi = [i+" " for i in prot_seq]
        linshi = "".join(linshi)
        linshi = linshi.strip(" ")
        new_prot_character.append(linshi)
        linshi = ""

    yeast_prot_data["text"] = new_prot_character
    yeast_prot_data["label"] =target
    yeast_prot_data = yeast_prot_data[["text","label"]]
    return yeast_prot_data


def sequence_padding(inputs, length=None, value=0, seq_dims=1, mode='post'):

    if length is None:
        length = np.max([np.shape(x)[:seq_dims] for x in inputs], axis=0)
    elif not hasattr(length, '__getitem__'):
        length = [length]

    slices = [np.s_[:length[i]] for i in range(seq_dims)]
    slices = tuple(slices) if len(slices) > 1 else slices[0]
    pad_width = [(0, 0) for _ in np.shape(inputs[0])]

    outputs = []
    for x in inputs:
        x = x[slices]
        for i in range(seq_dims):
            if mode == 'post':
                pad_width[i] = (0, length[i] - np.shape(x)[i])
            elif mode == 'pre':
                pad_width[i] = (length[i] - np.shape(x)[i], 0)
            else:
                raise ValueError('"mode" argument must be "post" or "pre".')
        x = np.pad(x, pad_width, 'constant', constant_values=value)
        outputs.append(x)
    return np.array(outputs)


class EntDataset(Dataset):
    def __init__(self, data, tokenizer, max_len):
        self.data = data
        self.tokenizer = tokenizer
        self.max_len = max_len

    def __len__(self):
        # print(889988,len(self.data['text']))
        return len(self.data['text'])

    def encoder(self, text, label):
        text = text
        # print(label)
       # try:
        label = [int(i) for i in label][:self.max_len - 2]
        #except:
        #    print(label)
        # print(1111,text,label)
        # encoder_text = self.tokenizer(' '.join([i for i in text]),  max_length=self.max_len, truncation=True)
        encoder_text = self.tokenizer(text, max_length=self.max_len, truncation=True)
        input_ids = encoder_text["input_ids"]
       # token_type_ids = encoder_text["token_type_ids"]  # RoBERTa does not require the NSP task.
        attention_mask = encoder_text["attention_mask"]

        return text, label, input_ids, attention_mask#, token_type_ids

   # def __getitem__(self, idx):
        # print(88888888,idx)
        #text, label = self.data["text"][idx], self.data["label"][idx]
        #return self.encoder(text, label)

    def __getitem__(self, idx):
        # For a single-row dataset, avoid accessing an index out of range
        if len(self.data) == 1:
            text, label = self.data["text"].iloc[0], self.data["label"].iloc[0]
        else:
            text, label = self.data["text"].iloc[idx], self.data["label"].iloc[idx]
        return self.encoder(text, label)

    @staticmethod
    def collate(examples):
        batch_token_ids, batch_labels, batch_mask_ids =  [], [], []

        text_list = []
        spo_list = []

        for item in examples:
            text, label, input_ids, attention_mask = item
            # print(torch.tensor(entity_labels).size())

            batch_token_ids.append(input_ids)
            batch_mask_ids.append(attention_mask)
            #batch_token_type_ids.append(token_type_ids)
            text_list.append(text)
            batch_labels.append(label)

        # print(sequence_padding(batch_token_ids))
        batch_token_ids = torch.tensor(sequence_padding(batch_token_ids)).long()
        batch_labels = torch.tensor(sequence_padding(batch_labels)).float()
        batch_mask_ids = torch.tensor(sequence_padding(batch_mask_ids)).float()
        #batch_token_type_ids = torch.tensor(sequence_padding(batch_token_type_ids)).long()  # RoBERTa does not require the NSP task.

        return text_list, batch_labels, batch_token_ids, batch_mask_ids#, batch_token_type_ids
