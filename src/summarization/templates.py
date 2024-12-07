KEY_IDEAS_TEMPLATE = """
Extract and list the key ideas from the content:

1. First key idea
2. Second key idea
...
N. Last key idea

Be concise and focus on the most important points.
"""

CONCEPTS_TEMPLATE = """
Break down the main concepts discussed:

A. Major Concept 1
   - Supporting point 1
   - Supporting point 2
   
B. Major Concept 2
   - Supporting point 1
   - Supporting point 2
...
"""

QUOTES_TEMPLATE = """
Extract significant quotes from the content:

1. "First important quote" - Speaker
2. "Second important quote" - Speaker
...
"""

ACTIONABLE_ITEMS_TEMPLATE = """
List actionable takeaways from the content:

1. First actionable item
2. Second actionable item
...
"""

EXPERIMENTAL_TEMPLATE = """
# Content Analysis

## One-Sentence Summary
[A single sentence that captures the essence of the content]

## Main Points
1. First main point
2. Second main point
...

## Key Takeaways
1. First takeaway
2. Second takeaway
...

## Tools & Technologies Mentioned
- Tool 1: Brief description
- Tool 2: Brief description
...
"""

PODCAST_SUMMARY_TEMPLATE = """You are an expert podcast summarizer. Create a detailed, structured summary of this podcast transcript that follows a mindmap format.

For each main topic discussed, provide:
1. The core concept/topic
2. Key supporting points and subtopics
3. Detailed explanations and examples
4. Practical takeaways or implications
5. Any relevant research, data, or expert opinions mentioned

Format the summary as follows:

# Main Topic 1
[One paragraph explaining the core concept]

## Supporting Points
1. [First supporting point with detailed explanation]
2. [Second supporting point with detailed explanation]
...

## Key Examples & Research
- [Detailed example or research finding]
- [Another example or finding]
...

## Practical Applications
[Paragraph about how to apply these insights]

[Repeat this structure for each main topic]

# Expert Insights & Quotes
[Notable quotes and expert insights, with context]

# Key Takeaways
[Comprehensive list of actionable insights and main lessons]

Remember to:
- Maintain depth and context in each explanation
- Include specific examples and evidence
- Connect ideas across topics where relevant
- Preserve important quotes and expert insights
- Focus on practical applications and implications

Transcript:
{text}

Summary:""" 