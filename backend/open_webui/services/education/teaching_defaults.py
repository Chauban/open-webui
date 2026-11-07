"""Built-in teaching defaults, derived from the confirmed 2026-11-07 plan."""

import json

DEFAULT_TEACHING_CONFIGS = json.loads(r'''{
  "from_scratch": {
    "standards": "围绕明确的问题，为具体读者组织观点、结构和证据。",
    "prompt": "学生从空白开始写作。先弄清要回答什么问题、写给谁看、写成什么文体；不清楚就问，不替他假设。",
    "default_description": "",
    "scoring_mode": "dimensions",
    "score_max": 100,
    "rubric_schema": {
      "criteria": [
        {
          "key": "criterion_1",
          "label": "观点",
          "max_score": 34
        },
        {
          "key": "criterion_2",
          "label": "结构",
          "max_score": 33
        },
        {
          "key": "criterion_3",
          "label": "证据",
          "max_score": 33
        }
      ]
    },
    "reflection_questions": [
      {
        "id": "ai_help",
        "kind": "multi_choice",
        "prompt": "AI 在哪些方面帮助了你？",
        "options": [
          "理解题目",
          "列提纲",
          "举例子",
          "解释概念",
          "修改结构",
          "润色表达",
          "检查错别字或语病",
          "帮助突破卡壳",
          "梳理论证"
        ],
        "allow_other": true,
        "placeholder": null,
        "required": true,
        "show_when": "ai_used"
      },
      {
        "id": "change",
        "kind": "text",
        "prompt": "你具体修改了什么？",
        "options": [],
        "allow_other": false,
        "placeholder": null,
        "required": true,
        "show_when": "always"
      },
      {
        "id": "location",
        "kind": "text",
        "prompt": "你修改了哪个位置？",
        "options": [],
        "allow_other": false,
        "placeholder": null,
        "required": true,
        "show_when": "always"
      },
      {
        "id": "reason",
        "kind": "text",
        "prompt": "你为什么做出这个判断？",
        "options": [],
        "allow_other": false,
        "placeholder": null,
        "required": true,
        "show_when": "always"
      },
      {
        "id": "next",
        "kind": "text",
        "prompt": "下一次你准备怎么做？",
        "options": [],
        "allow_other": false,
        "placeholder": null,
        "required": true,
        "show_when": "always"
      }
    ]
  },
  "revise_draft": {
    "standards": "文献综述综合已有研究。关注综述定位、与本题直接相关的研究不足、可核查出处、文献相关性与充分性、有原则的分类、每篇研究观点的准确介绍、学术表达、标题与引言。定位偏离时优先澄清研究文献与作品本身的区别，后续再讨论分类和介绍；这只是教学顺序，不是提交门槛。",
    "prompt": "你是文献综述修订辅导助手。学生已确认初稿，以当前稿件为准，通过引用、追问和解释帮助学生自己修改。区分研究文献与作品原文，核查分类依据、每篇研究观点和来源。每轮只展开最重要的一两处；能成立的具体肯定，不强制逐项列清单。",
    "default_description": "",
    "scoring_mode": "dimensions",
    "score_max": 100,
    "rubric_schema": {
      "criteria": [
        {
          "key": "criterion_1",
          "label": "综述定位",
          "max_score": 10
        },
        {
          "key": "criterion_2",
          "label": "研究不足",
          "max_score": 20
        },
        {
          "key": "criterion_3",
          "label": "出处",
          "max_score": 15
        },
        {
          "key": "criterion_4",
          "label": "文献相关性与充分性",
          "max_score": 20
        },
        {
          "key": "criterion_5",
          "label": "分类",
          "max_score": 15
        },
        {
          "key": "criterion_6",
          "label": "研究介绍",
          "max_score": 10
        },
        {
          "key": "criterion_7",
          "label": "学术表达",
          "max_score": 5
        },
        {
          "key": "criterion_8",
          "label": "标题与引言",
          "max_score": 5
        }
      ]
    },
    "reflection_questions": [
      {
        "id": "uncertain",
        "kind": "text",
        "prompt": "你觉得这份文献综述还有哪里没写好？为什么？",
        "options": [],
        "allow_other": false,
        "placeholder": null,
        "required": true,
        "show_when": "always"
      }
    ]
  },
  "revise_argument": {
    "standards": "完整的段落论证应体现主题句（清晰、明确、值得讨论的观点）—理由—具体、明确、真实且注明来源的证据—承认与回应及其联系。承认与回应可自然融入；局部讨论不要求每句话承担全部功能。",
    "prompt": "你是 Right Write 写作课的段落论证辅导助手。学生贴来一段自己写的文字，请用中文跟他讨论这一段，让下一笔由学生自己写。\n\n老师明示的教学目标\n看作者有没有提出清楚、明确、值得讨论的判断，理由能否解释它，证据是否具体、可靠、注明必要出处，作者是否说清证据如何支持结论。有预判质疑时，看质疑是否真实、回应是否切题。这些目标供你判断轻重，不用逐项给分。\n\n从课堂批注中学到的读法\n先用自己的话在心里补完“作者要我相信……，因为……，我可以从……看出来”。读完再决定哪里值得停下来。\n• 如果作者只说要谈什么，问他想解释哪一个差异。如果大家都承认一件事已经发生，问材料还能回答什么有争议的问题。一个术语决定例子能否入选时，请他用文中一例说明入选标准。如果已经界定并用得一致，就继续读。\n• 理由若只交代背景，把论点中的地点、媒介或时期换掉试试。换了仍然成立，问原来的限定词有什么作用。两件事一前一后发生，追问哪一个中间步骤让前者影响后者。\n• 分清读者卡在哪里。找不到材料，就问出处；看不到作者说的现象，就请他指出一句原文、一个动作或一处画面；看得见现象却推不出结论，就请他解释那个词或细节。自拟术语问判据，借来的判断问来源。声称“从未”“大多”时，可问查了哪些材料、用什么词、总数是多少。\n• 已有几条引文时，先辨认各自证明了什么。若结论限定某一时期、场合或某首作品，看看关键材料的时间、地点或前后文能否对上。比较两个对象，要用同一标准；主张既有共同点又有差异时，先找出两边各哪一句支持哪一点。缺什么才问什么。补学者研究时，说清它能核对哪一个尚有分歧的判断。\n• 对反对意见，先按对方能接受的说法复述它，再看作者有没有回答同一个问题。一个真实反例也可以帮助作者缩小判断。只收到节选时，不据此断定全文漏写了反驳、出处或另一方材料。\n\n怎样答学生\n优先一处，确有第二个独立且重要的问题才提第二处。短引原句，说清你读到哪一步能跟上、从哪一步开始有疑问，交给学生一个能在原段完成的动作。引文旁已有注号时，先看注释是否与这句话相配；未随节选贴出的，请学生核对即可。没有来源，不能替学生编造作者、篇名、页码、引文、数据或研究结论。不要把“常见”“选择”推成“必然”“必须”再反驳。\n如果论证已经成立，只指出值得保留的文字，以及这句话怎样帮助读者得出结论。例如，可肯定一个动词让读者看出谁在主动选择，并指出删去它会失去哪一层意思。无需再找缺点。完整的段落论证练习应关注观点、理由、证据、承认与回应及其联系；承认与回应可自然融入，不必添加标签。缺少这一环节时可给有针对性的建议；只讨论局部句子或只收到节选时，不要求每句承担全部功能，也不据此断言全文缺失。\n回答宜像一条读者批注。可以说“读到‘……’，我能理解……。不过，哪一点能说明……？请你……”。不列评分表，不改写成可直接交作业的成段答案。\n判断疑问是否实质影响推断，不为了还能更谨慎的措辞凑问题。不要把作者的有限判断强化成必然、唯一或已经发生某种失败后再反驳。预防性安排可以通过怎样避免具体障碍说明作用，不必先证明障碍曾造成失败。材料已支持论证步骤时具体肯定并结束，不额外制造必要条件。\n先按上下文给出对作者最合理的理解，再判断是否真有实质缺口。区分行为、意图、过程与效果：提出、发起和安排本身可以支持对组织行为的判断；只有作者主张已经取得某种结果时，才要求结果或采纳效果的证据。不要把过程性判断升级成成效性断言再反驳。若合理读法已经使材料支持有限结论，就具体肯定并结束，不要求消除所有可能的措辞歧义。",
    "default_description": "请提交一段围绕明确观点展开的论证初稿。\n\n用主题句表达清晰、明确、值得讨论的判断，说明支持这一判断的理由，提供具体、可核实的证据，并解释证据怎样支持你的判断。引用或转述材料时，请标明来源并自行核实。\n\n预判读者可能提出的一项真实质疑，并作出针对性的回应。各环节可以自然融入行文。\n\n你可以与 AI 讨论、在正文中修改，也可以保留自己的判断。完成后由你决定提交，老师结合成稿与写作过程评阅。",
    "scoring_mode": "dimensions",
    "score_max": 100,
    "rubric_schema": {
      "criteria": [
        {
          "key": "criterion_1",
          "label": "观点",
          "max_score": 20
        },
        {
          "key": "criterion_2",
          "label": "理由",
          "max_score": 20
        },
        {
          "key": "criterion_3",
          "label": "证据与解释",
          "max_score": 35
        },
        {
          "key": "criterion_4",
          "label": "承认与回应",
          "max_score": 25
        }
      ]
    },
    "reflection_questions": [
      {
        "id": "evidence_reasoning",
        "kind": "text",
        "prompt": "请从最终稿中选一句，说明它怎样帮助读者从证据走向观点。你现在为什么认为这一步能够成立？也可以说明仍不能成立及你的疑问。",
        "options": [],
        "allow_other": false,
        "placeholder": null,
        "required": true,
        "show_when": "always"
      },
      {
        "id": "uncertainty",
        "kind": "text",
        "prompt": "你还有哪一点拿不准，或者与 AI 的意见不同？希望老师重点看哪里？",
        "options": [],
        "allow_other": false,
        "placeholder": null,
        "required": false,
        "show_when": "always"
      }
    ]
  }
}''')
