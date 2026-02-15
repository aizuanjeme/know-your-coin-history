# 🪙 Coin History

## What Is This?

Imagine you have a **piggy bank** 🐷 with lots of coins inside. Each coin came from somewhere - maybe grandma gave you a dollar, maybe you found a quarter on the ground, or maybe mom gave you your allowance.

This program is like a **magic detective** 🔍 that helps you remember:
- Where did each coin come from?
- Who gave it to you?
- Where did THEY get it from?

---

## The Story of Bitcoin Coins

### 🏦 What's a "Wallet"?

Your Bitcoin wallet is like your piggy bank. It holds all your digital coins (we call them **UTXOs** - but let's just call them "coins").

### 📝 What's a "Transaction"?

When someone sends you a coin, that's called a **transaction**. It's like getting a birthday card with money inside! 🎂💵

The card says:
- Who sent it (the **input** - where the money came from)
- Who gets it (the **output** - that's you!)
- How much money

### 🔗 The Chain of Coins

Here's the cool part! Every coin has a **history**. 

Let's say:
1. **Grandma** had a coin 🪙
2. Grandma gave it to **Mom** 
3. Mom gave it to **You**!

Our magic detective can follow the trail backwards:
```
You ← Mom ← Grandma ← ??? (where did Grandma get it?)
```

This is called **tracing** the coin's history!

---

## How Our Program Works

### 🖥️ The Parts (Like LEGO Blocks!)

#### 1. **Bitcoin Talker** (`bitcoin_rpc.py`)
This is like a **telephone** 📞 that talks to Bitcoin.

```
Our Program: "Hey Bitcoin, tell me about this coin!"
Bitcoin: "Sure! Here's all the info..."
```

#### 2. **History Detective** (`coin_history.py`)
This is the **detective** 🕵️ that follows the trail!

It does these things:
- **Traces** coins back in time (like following footprints 👣)
- **Labels** coins so you remember them ("This is from Grandma!")
- **Spots clues** about where coins might have come from (fingerprints!)

#### 3. **The Website** (`app.py`)
This is like a **coloring book** with buttons! 🎨

You can:
- Click buttons to see your coins
- Draw pictures (graphs!) showing where coins came from
- Write notes (labels!) on your coins

#### 4. **The Picture Page** (`templates/index.html`)
This is what you SEE on the screen - the pretty colors and buttons!

---

## What Can You Do?

### 👀 See Your Coins
Click "Load UTXOs" and see all the coins in your piggy bank!

Each coin shows:
- 💰 How much it's worth
- 🏠 Its "address" (like a house number)
- 🎨 What "type" it is (different colors!)

### 🔍 Trace Where They Came From
Paste a coin's ID and click "Trace"!

You'll see a **picture** (graph) that shows:
- 🔵 Circles = Transactions (when coins moved)
- 🟩 Boxes = Individual coins
- ➡️ Arrows = The direction coins traveled

### 🏷️ Add Labels (Name Tags!)
Don't want to forget where a coin came from? Add a **label**!

Like putting a sticky note on your coin:
- "Birthday money from Grandma 🎂"
- "Allowance - January 💵"
- "Found on the ground! 🍀"

### 🔎 Find Clues (Fingerprints!)
The detective looks for **clues** about your coins:
- "This coin looks like it came from an old wallet!"
- "This coin was sent at a specific time!"
- "Multiple coin types mixed together - interesting! 🤔"

---

## The Types of Coins (Colors!)

| Type | Color | What It Means |
|------|-------|---------------|
| 🟡 P2PKH | Yellow | Old-style coin (like an antique!) |
| 🟠 P2SH | Orange | Wrapped coin (coin in a box) |
| 🔵 P2WPKH | Blue | Modern coin (newer and smaller!) |
| 🟣 P2WSH | Purple | Fancy wrapped coin |
| 🟢 P2TR | Green | Super modern coin (newest!) |
| 🔴 Coinbase | Red | Brand new coin (just created by miners!) |

---

## Summary

1. **Your coins live in a wallet** (piggy bank 🐷)
2. **Each coin has a history** (where it came from)
3. **Our detective traces the history** (follows the trail 👣)
4. **You can add labels** (sticky notes 📝)
5. **The website shows you everything** in pretty pictures! 🖼️

That's it! Now you know what "Know Your Coin History" does! 🎉
