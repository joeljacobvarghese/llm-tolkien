import json
import logging
from pathlib import Path
from typing import Callable, Mapping
import re

from datasets import Dataset
from transformers import AutoTokenizer, PreTrainedTokenizer

import sys

sys.path.append("/content/llm-tolkien")

from llm import config


LOGGER = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def prepare_dataset(dataset_path: Path, min_length: int, context_length: int, 
                    test_size: float, shuffle: bool, hf_repo: str) -> None:
    """Prepare dataset for training and push it to the hub.
    """
    tokenizer =  AutoTokenizer.from_pretrained(config.model_name)
    LOGGER.info(f'Start preparing dataset from {dataset_path}')
    text = preprocess_data(dataset_path=dataset_path, min_length=min_length, tokenizer=tokenizer)
    dataset = Dataset.from_dict({'text': [text]})
    # We push the extracted book publicly
    dataset.push_to_hub("SniiKz/Testdataset")
    tokenized_dataset = dataset.map(tokenize, batched=True, fn_kwargs={'tokenizer': tokenizer, 'context_length': context_length},
                                     remove_columns=dataset.column_names)
    LOGGER.info(f'The tokenized dataset is composed of {tokenized_dataset.num_rows} elements, each one composed of {context_length} tokens.')
    tokenized_dataset_dict = tokenized_dataset.train_test_split(test_size=test_size, shuffle=shuffle)
    LOGGER.info(f'The training dataset is composed of {tokenized_dataset_dict["train"].num_rows} elements, the test dataset is composed of {tokenized_dataset_dict["test"].num_rows} elements.')
    tokenized_dataset_dict.push_to_hub(hf_repo)
    LOGGER.info(f'Preparing dataset finished.')


def preprocess_data(dataset_path: Path, min_length: int, tokenizer: PreTrainedTokenizer) -> str:
    """Prepare dataset for training from the insurance document.

    Args:
        dataset_path (Path): Extracted text from the insurance document
        min_length (int): Filter pages without enough text
        tokenizer (PreTrainedTokenizer): HuggingFace tokenizer

    Yields:
        str: text of the pages
    """
    with open(dataset_path, 'r') as f:
        grouped_text = ""
        headings = []
        for line in f:
            elt = json.loads(line)
            text: str = list(elt.values())[0]
            if len(text) > min_length:
                # Check if the line is a heading (assumes headings end with a colon)
                if re.match(r'^[IVXLCDM]+[a-z]*\.\s.*:$|\d+\.\s.*:|\(.*\)\s.*:$', text.strip()):
                    headings.append(text.strip())
                else:
                    grouped_text += text

        # Combine the headings with the grouped_text
        for heading in headings:
            grouped_text = grouped_text.replace(heading, heading + " " + tokenizer.eos_token)

        # End of paragraphs defined by ".\n is transformed into EOS token"
        grouped_text = grouped_text.replace(".\n", "." + tokenizer.eos_token)

        return preprocess_text(grouped_text)


def preprocess_text(text: str) -> str:
    text = text.replace('\n', ' ')
    return text	


def tokenize(element: Mapping, tokenizer: Callable, context_length: int) -> str:
    inputs = tokenizer(element['text'], truncation=True, return_overflowing_tokens=True, 
                       return_length=True, max_length=context_length)
    inputs_batch = []
    for length, input_ids in zip(inputs['length'], inputs['input_ids']):
        if length == context_length: # We drop the last input_ids that are shorter than max_length
            inputs_batch.append(input_ids)
    return {"input_ids": inputs_batch}


if __name__ == '__main__':
    prepare_dataset(
        dataset_path=config.extraction_path, 
        min_length=config.min_length,
        context_length=config.context_length,
        test_size=config.test_size,
        shuffle=config.shuffle,
        hf_repo=config.hf_repo
    )
