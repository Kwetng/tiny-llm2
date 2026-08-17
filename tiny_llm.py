import torch

text = "the cat is sleeping the cat is eating"

words = text.split()

vocab = set(words)
vocab = sorted(vocab)

word_to_id = {
    "cat": 0,
    "eating": 1,
    "is": 2,
    "sleeping": 3,
    "the": 4
}

ids = [word_to_id[word] for word in words]

input_ids = ids[:3]
target_id = ids[3]

input_ids_2 = ids[4:7]
target_id_2 = ids[7]

x = torch.tensor(input_ids)

embedding = torch.nn.Embedding(5, 2)

output = torch.nn.Linear(2, 5)

learning_rate = 0.1

for epoch in range(100):
    for target in [3, 1]:

        emb = embedding(x)

        last = emb[-1]

        logits = output(last)

        probs = torch.softmax(logits, dim=0)

        loss = -torch.log(probs[target])

        loss.backward()

        output.weight.data -= learning_rate * output.weight.grad
        output.bias.data -= learning_rate * output.bias.grad
        embedding.weight.data -= learning_rate * embedding.weight.grad

        embedding.weight.grad.zero_()
        output.weight.grad.zero_()
        output.bias.grad.zero_()

test_emb = embedding(x)

test_last = test_emb[-1]

test_logits = output(test_last)

test_probs = torch.softmax(test_logits, dim=0)

print("Vocabulary:", vocab)
print("Probabilities:", test_probs)

predicted_id = torch.argmax(test_probs).item()

predicted_word = vocab[predicted_id]

print("Prediction:", predicted_word)