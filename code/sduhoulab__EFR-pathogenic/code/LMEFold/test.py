

import os
import random
import sys
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import DataLoader
from torchmetrics.classification import (
    BinaryF1Score, BinaryRecall, BinaryPrecision,
    BinarySpecificity, BinaryAccuracy, BinaryAUROC
)
from transformers import (
    AutoTokenizer, AutoModelForTokenClassification,
    BertTokenizer, BertForTokenClassification
)
import tqdm

#sys.path.append('/kaggle/input/zidingyi-xiuendata1')
from dataloader import EntDataset, get_data

MODEL_PATH = "facebook/esm2_t30_150M_UR50D"
WEIGHTS_PATH = './checkpoints/val_model_besteo_2_dp_0.1_lr_5e-05_bz_1.pkl' # Change to the actual path.

TEST_FILE = './data/test_data.csv'

BATCH_SIZE = 1
#MAX_LEN = 1024
MAX_LEN = 2048
DROPO = 0.1
SEED = 681
OUTPUT_DIR = './outputs'


def set_seed(seed: int = 681) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    os.environ['PYTHONHASHSEED'] = str(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False



class EpiAntModel(nn.Module):
    def __init__(self, model):
        super(EpiAntModel, self).__init__()
        self.model = model

    def forward(self, batch_token, batch_attention_mask):
        out = self.model(input_ids=batch_token, attention_mask=batch_attention_mask)
        return out['logits']


# ============================================================================
# Debug the function: Inspect the weight structure
# ============================================================================

def debug_weights_structure(weights_path: str):
    """Inspect the weight structure"""
    print("=" * 60)
    print("Inspect the weight structure")
    print("=" * 60)

    try:
        state_dict = torch.load(weights_path, map_location='cpu')

        print(f"Weight file path: {weights_path}")
        print(f"Total number of keys: {len(state_dict)}")

        print("\nFirst 20 keys:")
        for i, k in enumerate(list(state_dict.keys())[:20]):
            print(f"  {i+1:2d}. {k} -> shape: {state_dict[k].shape}")

        prefixes = {}
        for k in state_dict.keys():
            prefix = k.split('.')[0]
            prefixes[prefix] = prefixes.get(prefix, 0) + 1

        print("\nKey prefix statistics:")
        for prefix, count in prefixes.items():
            print(f"  {prefix}: {count}")

        return state_dict
    except Exception as e:
        print(f"Failed to load weight file: {e}")
        return None


# ============================================================================
# load model
# ============================================================================

def load_model(model_path: str, weights_path: str, dropo: float, device: torch.device):

    print(f"Loading pretrained model from: {model_path}")


    debug_weights_structure(weights_path)

    if 'esm' in model_path.lower():
        tokenizer = AutoTokenizer.from_pretrained(model_path, do_lower_case=False)
        base_model = AutoModelForTokenClassification.from_pretrained(
            model_path, num_labels=2, classifier_dropout=dropo
        )
    else:
        tokenizer = BertTokenizer.from_pretrained(model_path, do_lower_case=False)
        base_model = BertForTokenClassification.from_pretrained(
            model_path, num_labels=2, classifier_dropout=dropo
        )

    net = EpiAntModel(base_model)

    print(f"\nLoading weights from: {weights_path}")
    if not os.path.exists(weights_path):
        raise FileNotFoundError(f"Model weights not found: {weights_path}")


    state_dict = torch.load(weights_path, map_location=device)


    print("Attempting to load weights (strict=False)...")
    missing_keys, unexpected_keys = net.load_state_dict(state_dict, strict=False)

    print(f"Missing keys: {len(missing_keys)}")
    for k in missing_keys[:10]:
        print(f"  - {k}")
    if len(missing_keys) > 10:
        print(f"  ... and {len(missing_keys) - 10} more")

    print(f"\nUnexpected keys: {len(unexpected_keys)}")
    for k in unexpected_keys[:10]:
        print(f"  - {k}")
    if len(unexpected_keys) > 10:
        print(f"  ... and {len(unexpected_keys) - 10} more")


    if len(unexpected_keys) > 0 or len(missing_keys) > 0:
        print("\nAttempting to fix key names...")
        new_state_dict = {}
        for k, v in state_dict.items():

            if k.startswith('module.'):
                new_key = k[7:]
            elif k.startswith('model.'):
                new_key = k[6:]
            else:
                new_key = k
            new_state_dict[new_key] = v


        print("Reloading weights...")
        missing_keys2, unexpected_keys2 = net.load_state_dict(new_state_dict, strict=False)

        if len(missing_keys2) < len(missing_keys) or len(unexpected_keys2) < len(unexpected_keys):
            print("Key name fix succeeded!")
            print(f"After fix - Missing keys: {len(missing_keys2)}")
            print(f"After fix - Unexpected keys: {len(unexpected_keys2)}")

    net.to(device)
    net.eval()

    print("\nModel loaded successfully!")
    return net, tokenizer


# ============================================================================
# Test
# ============================================================================

def test_model(
    net: nn.Module,
    test_loader: DataLoader,
    device: torch.device
) -> Tuple[Dict, List]:

    f1fun = BinaryF1Score(ignore_index=-100).to(device)
    recallfun = BinaryRecall(ignore_index=-100).to(device)
    precisionfun = BinaryPrecision(ignore_index=-100).to(device)
    specificityfun = BinarySpecificity(ignore_index=-100).to(device)
    accfun = BinaryAccuracy(ignore_index=-100).to(device)
    aucfun = BinaryAUROC(thresholds=None, ignore_index=-100).to(device)


    f1fun.reset()
    recallfun.reset()
    precisionfun.reset()
    specificityfun.reset()
    accfun.reset()
    aucfun.reset()

    net.eval()
    all_predictions = []

    print("\n" + "="*60)
    print("Starting Test...")
    print("="*60)

    with torch.no_grad():
        for idx, batch in enumerate(tqdm.tqdm(test_loader, desc="Testing")):
            raw_text_list, labels, input_ids, attention_mask = batch
            input_ids = input_ids.to(device)
            attention_mask = attention_mask.to(device)
            labels = labels.to(device)


            out = net(input_ids, attention_mask)
            out = out[:, 1:-1, :]  # Remove [CLS] and [SEP]

            b, l, n = out.size()
            attention_mask = attention_mask[:, 1:-1]


            if attention_mask.size(1) > labels.size(1):
                attention_mask = attention_mask[:, :labels.size(1)]
            if out.size(1) > labels.size(1):
                out = out[:, :labels.size(1), :]


            labels = labels + (attention_mask - 1) * 100


            f1fun(out.argmax(dim=-1), labels.long())
            recallfun(out.argmax(dim=-1), labels.long())
            precisionfun(out.argmax(dim=-1), labels.long())
            specificityfun(out.argmax(dim=-1), labels.long())
            accfun(out.argmax(dim=-1), labels.long())
            aucfun(out[:, :, 1], labels.long())


            probabilities = torch.sigmoid(out[:, :, 1]).tolist()
            probabilities = [[round(p, 4) for p in prob] for prob in probabilities]

            for i in range(len(raw_text_list)):
                all_predictions.append({
                    'true_labels': labels[i].int().tolist(),
                    'pred_probs': probabilities[i],
                })


    results = {
        'auc': round(aucfun.compute().item(), 4),
        'acc': round(accfun.compute().item(), 4),
        'f1': round(f1fun.compute().item(), 4),
        'recall': round(recallfun.compute().item(), 4),
        'precision': round(precisionfun.compute().item(), 4),
        'specificity': round(specificityfun.compute().item(), 4),
    }

    return results, all_predictions



def main():

    set_seed(SEED)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")
    print(f"CUDA available: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"GPU: {torch.cuda.get_device_name(0)}")

    os.makedirs(OUTPUT_DIR, exist_ok=True)


    net, tokenizer = load_model(MODEL_PATH, WEIGHTS_PATH, DROPO, device)


    print(f"\nLoading test data from: {TEST_FILE}")
    test_data = get_data(TEST_FILE)
    print(f"Test samples: {len(test_data)}")

    test_dataset = EntDataset(test_data, tokenizer, max_len=MAX_LEN)
    test_loader = DataLoader(
        test_dataset, 
        batch_size=BATCH_SIZE, 
        collate_fn=test_dataset.collate, 
        shuffle=False
    )


    results, predictions = test_model(net, test_loader, device)


    print("\n" + "="*60)
    print("                    TEST RESULTS")
    print("="*60)
    print(f"  AUC:         {results['auc']:.4f}")
    print(f"  Accuracy:    {results['acc']:.4f}")
    print(f"  F1:          {results['f1']:.4f}")
    print(f"  Recall:      {results['recall']:.4f}")
    print(f"  Precision:   {results['precision']:.4f}")
    print(f"  Specificity: {results['specificity']:.4f}")
    print("="*60)


    results_df = pd.DataFrame([results])
    results_df.insert(0, 'type', 'default')
    metrics_path = os.path.join(OUTPUT_DIR, 'test_result.csv')
    results_df.to_csv(metrics_path, index=False)
    print(f"\nMetrics saved to: {metrics_path}")


    pred_df = pd.DataFrame(predictions)
    pred_df['auc'] = results['auc']
    pred_path = os.path.join(OUTPUT_DIR, 'predictions.csv')
    pred_df.to_csv(pred_path, index=False)
    print(f"Predictions saved to: {pred_path}")

    print("\nTesting Complete!")


if __name__ == "__main__":
    main()

