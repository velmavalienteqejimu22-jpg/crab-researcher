import MarketResearcherImg from '../assets/experts/MarketResearcher.png'
import EconomistImg from '../assets/experts/Economist.png'
import ContentStrategistImg from '../assets/experts/ContentStrategist.png'
import SocialMediaImg from '../assets/experts/SocialMedia.png'
import PaidAdsImg from '../assets/experts/PaidAds.png'
import PartnershipsImg from '../assets/experts/Partnerships.png'
import AIDistributionImg from '../assets/experts/AIDistribution.png'
import PsychologistImg from '../assets/experts/Psychologist.png'
import ProductGrowthImg from '../assets/experts/ProductGrowth.png'
import DataAnalystImg from '../assets/experts/DataAnalyst.png'
import CopywriterImg from '../assets/experts/Copywriter.png'
import StrategyCriticImg from '../assets/experts/StrategyCritic.png'
import DesignerImg from '../assets/experts/Designer.png'

export interface ExpertInfo {
  name: string;
  short: string;
  color: string;
  icon: string;
  avatar: string;
}

export const EXPERTS: Record<string, ExpertInfo> = {
  market_researcher: { name: 'Market Researcher', short: 'Research', color: '#0EA5E9', icon: '🔍', avatar: MarketResearcherImg },
  economist: { name: 'Economist', short: 'Econ', color: '#10B981', icon: '💰', avatar: EconomistImg },
  content_strategist: { name: 'Content Strategist', short: 'Content', color: '#8B5CF6', icon: '📝', avatar: ContentStrategistImg },
  social_media: { name: 'Social Media', short: 'Social', color: '#F43F5E', icon: '🎯', avatar: SocialMediaImg },
  paid_ads: { name: 'Paid Ads', short: 'Ads', color: '#F59E0B', icon: '📢', avatar: PaidAdsImg },
  partnerships: { name: 'Partnerships', short: 'Partners', color: '#EC4899', icon: '🤝', avatar: PartnershipsImg },
  ai_distribution: { name: 'AI Distribution', short: 'AI Dist', color: '#6366F1', icon: '🤖', avatar: AIDistributionImg },
  psychologist: { name: 'Psychologist', short: 'Psych', color: '#14B8A6', icon: '🧠', avatar: PsychologistImg },
  product_growth: { name: 'Product Growth', short: 'Growth', color: '#F97316', icon: '📈', avatar: ProductGrowthImg },
  data_analyst: { name: 'Data Analyst', short: 'Data', color: '#64748B', icon: '📊', avatar: DataAnalystImg },
  copywriter: { name: 'Copywriter', short: 'Copy', color: '#A855F7', icon: '✍️', avatar: CopywriterImg },
  critic: { name: 'Strategy Critic', short: 'Critic', color: '#EF4444', icon: '⚖️', avatar: StrategyCriticImg },
  designer: { name: 'Designer', short: 'Design', color: '#06B6D4', icon: '🎨', avatar: DesignerImg },
}
